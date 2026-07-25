"""RED-first tests for the Docker-backed Postgres capture adapter."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, NamedTuple, NoReturn, cast

import pytest

from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_artifacts.contracts import ArtifactComponentKind
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge_postgres_docker import capture as capture_module
from odoo_forge_postgres_docker.capture import (
    CAPTURE_APPLICATION_NAME_PREFIX,
    MIN_STAGING_FREE_BYTES,
    ORPHAN_STAGED_FILE_MAX_AGE_SECONDS,
    CaptureBinaryUnavailableError,
    CaptureCommandFailedError,
    CapturePersistenceError,
    CaptureRunResult,
    CaptureStagingSpaceError,
    CaptureTimeoutError,
    DockerPostgresqlCaptureAdapter,
    InvalidCaptureIdentifierError,
    reap_orphaned_staged_files,
    terminate_in_container_backend,
)
from odoo_forge_postgres_docker.staged_store import (
    FilesystemStagedArtifactStore,
    StagedArtifactError,
)

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class _DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def _disk_usage_stub(*, free: int) -> Callable[[object], _DiskUsage]:
    """Return a `shutil.disk_usage` double reporting exactly `free` free bytes."""
    return lambda _path: _DiskUsage(total=free * 2, used=free, free=free)


def _source(target_id: str = "odoo-source") -> CaptureSource:
    return CaptureSource(
        credentials=CredentialHandle("source-handle"),
        target=TargetContext(kind="source", target_id=target_id),
    )


def _write_staged_file(stdout: bytes) -> Path:
    """Create a real temp file with `stdout` bytes, mirroring `_run_subprocess`'s own
    staging shape, so `store.stage`'s move-into-custody has a real source to move."""
    with tempfile.NamedTemporaryFile(prefix="odoo-forge-capture-test-", delete=False) as staged:
        staged.write(stdout)
        return Path(staged.name)


class _RecordingRunner:
    def __init__(self, stdout: bytes = b"dump-bytes", returncode: int = 0) -> None:
        self.calls: list[Sequence[str]] = []
        self._stdout = stdout
        self._returncode = returncode
        self.last_staged_path: Path | None = None

    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        self.calls.append(list(argv))
        staged_path = _write_staged_file(self._stdout)
        self.last_staged_path = staged_path
        return CaptureRunResult(
            returncode=self._returncode,
            digest_hex=hashlib.sha256(self._stdout).hexdigest(),
            staged_path=staged_path,
        )


class _MissingBinaryRunner:
    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        raise FileNotFoundError("docker")


class _TimeoutRunner:
    """Raises `TimeoutExpired` on the (pg_dump) call."""

    def __init__(self) -> None:
        self.calls: list[Sequence[str]] = []

    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        self.calls.append(list(argv))
        raise subprocess.TimeoutExpired(list(argv), timeout)


class _PutFailingStore:
    """A store whose `put` always fails BEFORE `stage` is ever reached, proving
    the reordered persistence (`put` before `stage`) never orphans a blob: no
    blob is moved into custody when the manifest was never persisted."""

    def __init__(self) -> None:
        self.put_calls: list[object] = []
        self.stage_calls: list[Path] = []

    def put(self, ref: object, manifest: object) -> None:
        self.put_calls.append(ref)
        raise RuntimeError("simulated put failure")

    def stage(self, digest: object, source_path: Path) -> None:
        self.stage_calls.append(source_path)
        source_path.unlink()

    def resolve(self, ref: object) -> object:
        raise NotImplementedError

    def open_component(self, component: object) -> Path:
        raise NotImplementedError

    def discard(self, ref: object) -> object:
        raise NotImplementedError


class _StageFailingStore:
    """A store whose `put` succeeds but `stage` then fails, proving the
    compensating `discard(ref)` reaps the persisted-but-unstaged manifest —
    no new store API surface beyond the existing `discard(ref)` contract."""

    def __init__(self) -> None:
        self.put_calls: list[object] = []
        self.stage_calls: list[Path] = []
        self.discard_calls: list[object] = []

    def put(self, ref: object, manifest: object) -> None:
        self.put_calls.append(ref)

    def stage(self, digest: object, source_path: Path) -> None:
        self.stage_calls.append(source_path)
        raise RuntimeError("simulated stage failure")

    def resolve(self, ref: object) -> object:
        raise NotImplementedError

    def open_component(self, component: object) -> Path:
        raise NotImplementedError

    def discard(self, ref: object) -> object:
        self.discard_calls.append(ref)
        return None


def _store(tmp_path: Path) -> FilesystemStagedArtifactStore:
    return FilesystemStagedArtifactStore(tmp_path / "artifact-store")


def test_capture_runs_pg_dump_argv_only_and_computes_digest_before_return(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner(stdout=b"dump-bytes")
    adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

    manifest = adapter.capture(_source())

    assert len(runner.calls) == 1
    argv = list(runner.calls[0])
    assert argv[:-1] == [
        "docker",
        "exec",
        "odoo-source",
        "pg_dump",
        "-U",
        "postgres",
        "--format=custom",
    ]
    # The dbname is passed as a libpq conninfo string so the invocation carries a
    # unique `application_name` a timeout can reap in-container (follow-up #153).
    assert argv[-1].startswith(
        f"dbname=odoo-source application_name={CAPTURE_APPLICATION_NAME_PREFIX}"
    )
    for recorded in runner.calls:
        assert isinstance(recorded, list)
        assert all(isinstance(item, str) for item in recorded)

    database = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert database.digest.value == hashlib.sha256(b"dump-bytes").hexdigest()


def test_capture_emits_empty_filestore_component_with_empty_v1_format(tmp_path: Path) -> None:
    runner = _RecordingRunner()
    adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

    manifest = adapter.capture(_source())

    filestore = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.FILESTORE
    )
    assert filestore.format_version == "empty-v1"
    assert filestore.digest.value == _EMPTY_SHA256
    assert filestore.digest.algorithm == "sha256"


@pytest.mark.parametrize(
    "unsafe_target_id",
    [
        "odoo; rm -rf /",
        "odoo && echo pwned",
        "odoo$(whoami)",
        "odoo source",
        "Odoo-Source",
    ],
)
def test_capture_rejects_unsafe_source_identifiers_before_invoking_runner(
    unsafe_target_id: str, tmp_path: Path
) -> None:
    runner = _RecordingRunner()
    adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

    with pytest.raises(InvalidCaptureIdentifierError) as exc_info:
        adapter.capture(_source(unsafe_target_id))

    assert runner.calls == []
    assert str(exc_info.value) == InvalidCaptureIdentifierError.public_detail


def test_capture_nonzero_returncode_raises_distinct_capture_command_failed_error(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner(returncode=1)
    adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

    with pytest.raises(CaptureCommandFailedError) as exc_info:
        adapter.capture(_source())

    assert str(exc_info.value) == CaptureCommandFailedError.public_detail
    assert runner.last_staged_path is not None
    assert not runner.last_staged_path.exists()


def test_capture_missing_docker_binary_raises_distinct_capture_binary_unavailable_error(
    tmp_path: Path,
) -> None:
    adapter = DockerPostgresqlCaptureAdapter(runner=_MissingBinaryRunner(), store=_store(tmp_path))

    with pytest.raises(CaptureBinaryUnavailableError) as exc_info:
        adapter.capture(_source())

    assert str(exc_info.value) == CaptureBinaryUnavailableError.public_detail


def test_capture_timeout_raises_distinct_capture_timeout_error(tmp_path: Path) -> None:
    runner = _TimeoutRunner()
    adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

    with pytest.raises(CaptureTimeoutError) as exc_info:
        adapter.capture(_source())

    assert str(exc_info.value) == CaptureTimeoutError.public_detail
    assert len(runner.calls) == 1
    for argv in runner.calls:
        assert isinstance(argv, list)
        assert all(isinstance(item, str) for item in argv)


def test_capture_default_runner_invokes_subprocess_run_argv_only_never_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured_kwargs: dict[str, object] = {}

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured_kwargs.update(kwargs)
        stdout = cast("IO[bytes]", kwargs["stdout"])
        stdout.write(b"")
        return subprocess.CompletedProcess(list(argv), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

    adapter.capture(_source())

    assert captured_kwargs["shell"] is False
    assert "timeout" in captured_kwargs


def test_default_runner_hashes_staged_file_in_bounded_chunks_without_full_buffering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Follow-up #153 item 4: the payload must be LARGER than one read chunk, so the
    multi-chunk `while chunk := readback.read(...)` loop is genuinely exercised and a
    hash fed only the first chunk would fail. `_CHUNK_SIZE` is shrunk rather than
    writing a multi-MiB fixture, keeping the test fast while crossing real boundaries.
    """
    monkeypatch.setattr(capture_module, "_CHUNK_SIZE", 8)
    # 31 bytes over an 8-byte chunk: 3 full chunks plus a 7-byte partial tail, so the
    # loop terminates on a short read rather than an exact boundary.
    full = b"".join([b"chunk-one-", b"chunk-two-", b"chunk-three"])
    assert len(full) == 31

    read_sizes: list[int] = []

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        stdout = cast("IO[bytes]", kwargs["stdout"])
        stdout.write(full)
        stdout.flush()
        return subprocess.CompletedProcess(list(argv), returncode=0)

    class _CountingHasher:
        def __init__(self) -> None:
            self._inner = hashlib.new("sha256")

        def update(self, chunk: bytes) -> None:
            read_sizes.append(len(chunk))
            self._inner.update(chunk)

        def hexdigest(self) -> str:
            return self._inner.hexdigest()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(hashlib, "sha256", lambda: _CountingHasher())
    adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

    manifest = adapter.capture(_source())

    database = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert database.digest.value == hashlib.new("sha256", full).hexdigest()
    assert read_sizes[:4] == [8, 8, 8, 7], "multi-chunk read path must be exercised"


def test_default_runner_raises_capture_timeout_when_real_subprocess_run_times_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exercises the REAL `_run_subprocess`, not a runner double: a genuinely
    stalled producer (no output ever written) must still surface as
    `CaptureTimeoutError`, proving the timeout is enforced by
    `subprocess.run(..., timeout=)` itself rather than a hand-rolled loop
    that only checks a deadline between blocking reads.
    """

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(list(argv), cast("float", kwargs["timeout"]))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

    with pytest.raises(CaptureTimeoutError):
        adapter.capture(_source())


def test_default_runner_does_not_unlink_staged_file_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Design D9: on the success path `_run_subprocess` itself must not delete
    the staged temp file — persistence is `capture()`'s responsibility."""
    observed: dict[str, Path] = {}
    from odoo_forge_postgres_docker import capture as capture_module

    original_run_subprocess = capture_module._run_subprocess

    def _spy_runner(argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        result = original_run_subprocess(argv, timeout=timeout)
        observed["staged_path"] = result.staged_path
        assert result.staged_path.exists()
        return result

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        stdout = cast("IO[bytes]", kwargs["stdout"])
        stdout.write(b"payload")
        return subprocess.CompletedProcess(list(argv), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter(runner=_spy_runner, store=_store(tmp_path))

    adapter.capture(_source())

    assert "staged_path" in observed


class TestCapturePersistsIntoStagedArtifactStore:
    """Bridge slice B3 (design D9): capture persists into a `StagedArtifactStore`
    instead of deleting the temp file — a captured manifest must be resolvable
    from the store afterward, with real bytes matching the recorded digest."""

    def test_captured_manifest_round_trips_through_the_store(self, tmp_path: Path) -> None:
        payload = b"real-dump-bytes-for-round-trip"
        runner = _RecordingRunner(stdout=payload)
        store = _store(tmp_path)
        adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=store)

        manifest = adapter.capture(_source())

        database = next(
            component
            for component in manifest.components
            if component.kind is ArtifactComponentKind.DATABASE
        )
        resolved_path = store.open_component(database)
        assert resolved_path.read_bytes() == payload
        assert database.digest.value == hashlib.sha256(payload).hexdigest()

    def test_manifest_is_persisted_under_its_restore_set_id(self, tmp_path: Path) -> None:
        runner = _RecordingRunner(stdout=b"dump-bytes")
        store = _store(tmp_path)
        adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=store)

        manifest = adapter.capture(_source())

        resolved = store.resolve(DataArtifactRef(manifest.restore_set_id))
        assert resolved == manifest

    def test_staged_temp_file_is_moved_not_left_behind_on_success(self, tmp_path: Path) -> None:
        runner = _RecordingRunner(stdout=b"dump-bytes")
        adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

        adapter.capture(_source())

        assert runner.last_staged_path is not None
        assert not runner.last_staged_path.exists()

    def test_staged_temp_file_is_unlinked_when_put_fails_before_staging(
        self, tmp_path: Path
    ) -> None:
        payload = b"dump-bytes"
        runner = _RecordingRunner(stdout=payload)
        failing_store = _PutFailingStore()
        adapter = DockerPostgresqlCaptureAdapter(
            runner=runner, store=cast("StagedArtifactStore", failing_store)
        )

        with pytest.raises(CapturePersistenceError):
            adapter.capture(_source())

        assert runner.last_staged_path is not None
        assert not runner.last_staged_path.exists()
        # `put` is attempted, but since it fails first, `stage` never runs — so
        # no blob is ever moved into custody, and nothing is orphaned.
        assert failing_store.put_calls
        assert failing_store.stage_calls == []

    def test_no_orphaned_blob_when_stage_fails_after_put_succeeds(self, tmp_path: Path) -> None:
        """RED (review finding 2): with `put` reordered before `stage`, a `stage`
        failure after a successful `put` is compensated by `discard(ref)` — no
        new store API needed, and `capture()` still raises (no false success)."""
        payload = b"dump-bytes"
        runner = _RecordingRunner(stdout=payload)
        stage_failing_store = _StageFailingStore()
        adapter = DockerPostgresqlCaptureAdapter(
            runner=runner, store=cast("StagedArtifactStore", stage_failing_store)
        )

        with pytest.raises(CapturePersistenceError):
            adapter.capture(_source())

        assert stage_failing_store.put_calls
        assert stage_failing_store.stage_calls
        assert stage_failing_store.discard_calls == stage_failing_store.put_calls

    def test_no_orphaned_manifest_when_the_real_store_fails_to_stage(self, tmp_path: Path) -> None:
        """Follow-up #161: the compensation above is proven against a MOCK store, so it
        only shows `capture()` calls `discard`. This proves the outcome against the real
        `FilesystemStagedArtifactStore`: an unwritable blobs directory fails `stage`
        after `put` already succeeded, and the compensation must leave no resolvable
        manifest pointing at bytes that were never staged."""
        store = _store(tmp_path)
        # `put` writes under `manifests/`; `stage` writes under `blobs/`. Pre-creating
        # `blobs/` read-only fails exactly one of the two, in the required order.
        blobs_dir = tmp_path / "artifact-store" / "blobs"
        blobs_dir.mkdir(parents=True)
        blobs_dir.chmod(0o500)
        adapter = DockerPostgresqlCaptureAdapter(
            runner=_RecordingRunner(stdout=b"dump-bytes"), store=store
        )

        try:
            with pytest.raises(CapturePersistenceError):
                adapter.capture(_source())

            with pytest.raises(StagedArtifactError):
                store.resolve(DataArtifactRef("restore-set-odoo-source"))
        finally:
            blobs_dir.chmod(0o700)

    def test_a_failed_compensation_chains_both_failures_rather_than_swallowing_one(
        self, tmp_path: Path
    ) -> None:
        """Follow-up #161: the compensating `discard` was `suppress(Exception)` in a
        module with no logger, so a failed compensation vanished without a trace. Both
        failures must now reach the caller through the raised error's cause chain."""

        class _StageAndDiscardFailingStore(_StageFailingStore):
            def discard(self, ref: object) -> object:
                super().discard(ref)
                raise RuntimeError("simulated discard failure")

        adapter = DockerPostgresqlCaptureAdapter(
            runner=_RecordingRunner(stdout=b"dump-bytes"),
            store=cast("StagedArtifactStore", _StageAndDiscardFailingStore()),
        )

        with pytest.raises(CapturePersistenceError) as exc_info:
            adapter.capture(_source())

        cause = exc_info.value.__cause__
        assert isinstance(cause, ExceptionGroup)
        messages = {str(inner) for inner in cause.exceptions}
        assert messages == {"simulated stage failure", "simulated discard failure"}

    def test_persistence_failure_surfaces_as_capture_persistence_error(
        self, tmp_path: Path
    ) -> None:
        """RED (review finding 3): a raw `StagedArtifactError` (or any other
        store failure) is never allowed to escape `capture()` — it is always
        remapped to the Capture* taxonomy."""
        runner = _RecordingRunner(stdout=b"dump-bytes")
        failing_store = _PutFailingStore()
        adapter = DockerPostgresqlCaptureAdapter(
            runner=runner, store=cast("StagedArtifactStore", failing_store)
        )

        with pytest.raises(CapturePersistenceError) as exc_info:
            adapter.capture(_source())

        assert str(exc_info.value) == CapturePersistenceError.public_detail
        assert not isinstance(exc_info.value, RuntimeError)


class TestCaptureStagedTempFileSingleOwnerCleanup:
    """Bridge slice B3 correction (review finding 1): the staged temp file has a
    single owner per stage — no leak window between hashing, manifest
    construction, and persistence."""

    def test_hash_readback_failure_cleans_the_staged_temp_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """RED: previously, a hash-readback failure inside `_run_subprocess` was
        OUTSIDE any try/finally (a regression vs. the prior `finally`-wrapped
        version), leaking the staged temp file."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            stdout = cast("IO[bytes]", kwargs["stdout"])
            stdout.write(b"some-bytes")
            return subprocess.CompletedProcess(list(argv), returncode=0)

        class _BoomHasher:
            def update(self, chunk: bytes) -> None:
                raise OSError("simulated hash readback failure")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(hashlib, "sha256", lambda: _BoomHasher())
        adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

        before = set(Path(tempfile.gettempdir()).glob("odoo-forge-capture-*"))
        with pytest.raises(OSError):
            adapter.capture(_source())
        after = set(Path(tempfile.gettempdir()).glob("odoo-forge-capture-*"))

        assert after - before == set()

    def test_manifest_construction_failure_cleans_the_staged_temp_file(
        self, tmp_path: Path
    ) -> None:
        """RED: previously, if manifest construction raised between `_run()` and
        `_persist()`, the staged temp file was neither unlinked nor moved."""
        runner = _RecordingRunner(stdout=b"dump-bytes")

        def _boom_filestore_seam() -> NoReturn:
            raise ValueError("simulated manifest construction failure")

        adapter = DockerPostgresqlCaptureAdapter(
            runner=runner,
            store=_store(tmp_path),
            filestore_seam=_boom_filestore_seam,
        )

        with pytest.raises(ValueError):
            adapter.capture(_source())

        assert runner.last_staged_path is not None
        assert not runner.last_staged_path.exists()

    def test_real_runner_timeout_cleans_the_staged_temp_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Follow-up #153 item 5: the timeout failure path is asserted against the
        REAL `_run_subprocess`, where a staged temp file genuinely exists."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            stdout = cast("IO[bytes]", kwargs["stdout"])
            stdout.write(b"partial-dump")
            raise subprocess.TimeoutExpired(list(argv), cast("float", kwargs["timeout"]))

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path), reaper=lambda _c, _a: None)

        with pytest.raises(CaptureTimeoutError):
            adapter.capture(_source())

        assert list(tmp_path.glob("odoo-forge-capture-*")) == []

    def test_real_runner_missing_binary_cleans_the_staged_temp_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Follow-up #153 item 5: same for the missing-`docker` failure path."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise FileNotFoundError("docker")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

        with pytest.raises(CaptureBinaryUnavailableError):
            adapter.capture(_source())

        assert list(tmp_path.glob("odoo-forge-capture-*")) == []


class TestCaptureInContainerBackendReaping:
    """Follow-up #153 item 1: killing the local `docker exec` client does not reap
    the in-container `pg_dump`. Each invocation tags its libpq connection with a
    unique `application_name`, so a timeout can terminate exactly that backend."""

    def test_capture_tags_the_invocation_with_a_unique_application_name(
        self, tmp_path: Path
    ) -> None:
        runner = _RecordingRunner()
        adapter = DockerPostgresqlCaptureAdapter(runner=runner, store=_store(tmp_path))

        adapter.capture(_source())
        adapter.capture(_source())

        conninfos = [argv[-1] for argv in runner.calls]
        application_names = [conninfo.split("application_name=")[1] for conninfo in conninfos]
        assert all(conninfo.startswith("dbname=odoo-source ") for conninfo in conninfos)
        assert all(name.startswith(CAPTURE_APPLICATION_NAME_PREFIX) for name in application_names)
        assert len(set(application_names)) == 2, "each invocation must be uniquely tagged"

    def test_timeout_reaps_the_backend_for_exactly_that_invocation(self, tmp_path: Path) -> None:
        runner = _TimeoutRunner()
        reaped: list[tuple[str, str]] = []
        adapter = DockerPostgresqlCaptureAdapter(
            runner=runner,
            store=_store(tmp_path),
            reaper=lambda container, application_name: reaped.append((container, application_name)),
        )

        with pytest.raises(CaptureTimeoutError):
            adapter.capture(_source())

        assert len(reaped) == 1
        container, application_name = reaped[0]
        assert container == "odoo-source"
        assert application_name in runner.calls[0][-1]

    def test_successful_capture_never_reaps(self, tmp_path: Path) -> None:
        reaped: list[tuple[str, str]] = []
        adapter = DockerPostgresqlCaptureAdapter(
            runner=_RecordingRunner(),
            store=_store(tmp_path),
            reaper=lambda container, application_name: reaped.append((container, application_name)),
        )

        adapter.capture(_source())

        assert reaped == []

    def test_reaper_failure_never_masks_the_capture_timeout(self, tmp_path: Path) -> None:
        """The reaper is best-effort: a dead container or a missing `psql` must not
        replace the caller-meaningful `CaptureTimeoutError` with a reaper error."""

        def _boom_reaper(_container: str, _application_name: str) -> NoReturn:
            raise RuntimeError("simulated reaper failure")

        adapter = DockerPostgresqlCaptureAdapter(
            runner=_TimeoutRunner(), store=_store(tmp_path), reaper=_boom_reaper
        )

        with pytest.raises(CaptureTimeoutError):
            adapter.capture(_source())

    def test_default_reaper_terminates_the_matching_backend_argv_only_and_bounded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: dict[str, object] = {}

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            recorded["argv"] = list(argv)
            recorded.update(kwargs)
            return subprocess.CompletedProcess(list(argv), returncode=0)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        terminate_in_container_backend("odoo-source", f"{CAPTURE_APPLICATION_NAME_PREFIX}abc123")

        argv = cast("list[str]", recorded["argv"])
        assert argv[:5] == ["docker", "exec", "odoo-source", "psql", "-U"]
        assert "pg_terminate_backend" in argv[-1]
        assert f"{CAPTURE_APPLICATION_NAME_PREFIX}abc123" in argv[-1]
        assert recorded["shell"] is False
        assert isinstance(recorded["timeout"], float)

    def test_default_reaper_swallows_subprocess_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_run(argv: Sequence[str], **kwargs: object) -> NoReturn:
            raise FileNotFoundError("docker")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        terminate_in_container_backend("odoo-source", f"{CAPTURE_APPLICATION_NAME_PREFIX}abc123")

    def test_default_reaper_rejects_an_unsafe_application_name(self) -> None:
        """The application name is interpolated into a SQL literal, so it is
        validated rather than trusted — it never originates from user input, but
        the guard keeps that invariant mechanical."""
        with pytest.raises(InvalidCaptureIdentifierError):
            terminate_in_container_backend("odoo-source", "capture'; DROP TABLE x; --")


class TestCaptureStagingDiskSpaceGuard:
    """Follow-up #153 item 2: a constrained `/tmp` (tmpfs containers) filling
    mid multi-GB dump surfaced a generic error. A pre-flight free-space floor
    turns that into an explicit, diagnosable signal."""

    def test_capture_refuses_to_stage_below_the_free_space_floor(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _fake_run(argv: Sequence[str], **kwargs: object) -> NoReturn:
            raise AssertionError("subprocess must never start below the free-space floor")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(shutil, "disk_usage", _disk_usage_stub(free=1))
        adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

        with pytest.raises(CaptureStagingSpaceError) as exc_info:
            adapter.capture(_source())

        assert str(exc_info.value) == CaptureStagingSpaceError.public_detail

    def test_capture_proceeds_above_the_free_space_floor(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            stdout = cast("IO[bytes]", kwargs["stdout"])
            stdout.write(b"payload")
            return subprocess.CompletedProcess(list(argv), returncode=0)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(shutil, "disk_usage", _disk_usage_stub(free=MIN_STAGING_FREE_BYTES * 4))
        adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

        assert adapter.capture(_source()) is not None

    def test_an_unreadable_staging_directory_never_blocks_a_capture(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The guard is advisory: if free space cannot be determined, capture
        proceeds rather than failing closed on a diagnostic."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            stdout = cast("IO[bytes]", kwargs["stdout"])
            stdout.write(b"payload")
            return subprocess.CompletedProcess(list(argv), returncode=0)

        def _boom_disk_usage(_path: str) -> NoReturn:
            raise OSError("simulated statvfs failure")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(shutil, "disk_usage", _boom_disk_usage)
        adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

        assert adapter.capture(_source()) is not None


class TestOrphanedStagedFileReaper:
    """Follow-up #153 item 3: a SIGKILLed/OOM-killed parent leaves its
    `odoo-forge-capture-*` temp file behind with no owner left to clean it."""

    def _aged(self, path: Path, age_seconds: float) -> None:
        stale = time.time() - age_seconds
        os.utime(path, (stale, stale))

    def test_reaps_stale_capture_temp_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        orphan = tmp_path / "odoo-forge-capture-abc"
        orphan.write_bytes(b"orphaned dump")
        self._aged(orphan, ORPHAN_STAGED_FILE_MAX_AGE_SECONDS * 2)

        reap_orphaned_staged_files()

        assert not orphan.exists()

    def test_keeps_capture_temp_files_younger_than_the_age_floor(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A concurrently running capture's staged file must never be reaped."""
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        live = tmp_path / "odoo-forge-capture-live"
        live.write_bytes(b"in-flight dump")

        reap_orphaned_staged_files()

        assert live.exists()

    def test_never_touches_unrelated_temp_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        unrelated = tmp_path / "some-other-tool-file"
        unrelated.write_bytes(b"not ours")
        self._aged(unrelated, ORPHAN_STAGED_FILE_MAX_AGE_SECONDS * 10)

        reap_orphaned_staged_files()

        assert unrelated.exists()

    def test_capture_reaps_orphans_before_running(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        orphan = tmp_path / "odoo-forge-capture-abc"
        orphan.write_bytes(b"orphaned dump")
        self._aged(orphan, ORPHAN_STAGED_FILE_MAX_AGE_SECONDS * 2)
        adapter = DockerPostgresqlCaptureAdapter(runner=_RecordingRunner(), store=_store(tmp_path))

        adapter.capture(_source())

        assert not orphan.exists()

    def test_an_in_flight_file_is_never_reaped_by_a_longer_running_capture(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Follow-up #175 item 6: the 24h floor assumed a capture is bounded at an hour,
        but `timeout` is caller-overridable for very large sources. A capture configured
        to run longer than the floor could have its still-being-written staged file
        unlinked by a CONCURRENT capture's sweep, and the live readback would then fail
        with an unrelated FileNotFoundError."""
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        in_flight = tmp_path / "odoo-forge-capture-inflight"
        in_flight.write_bytes(b"a capture still writing this")
        # Older than the fixed floor, but well inside a 48h-timeout capture's own window.
        self._aged(in_flight, ORPHAN_STAGED_FILE_MAX_AGE_SECONDS * 1.5)
        adapter = DockerPostgresqlCaptureAdapter(
            runner=_RecordingRunner(),
            store=_store(tmp_path),
            timeout=ORPHAN_STAGED_FILE_MAX_AGE_SECONDS * 2,
        )

        adapter.capture(_source())

        assert in_flight.exists(), "a file younger than this adapter's own bound must survive"

    def test_the_floor_still_applies_for_a_short_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The timeout-derived window only ever RAISES the floor; a default-timeout
        adapter must still reap genuine 24h-old orphans."""
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        orphan = tmp_path / "odoo-forge-capture-orphan"
        orphan.write_bytes(b"orphaned")
        self._aged(orphan, ORPHAN_STAGED_FILE_MAX_AGE_SECONDS * 2)
        adapter = DockerPostgresqlCaptureAdapter(
            runner=_RecordingRunner(), store=_store(tmp_path), timeout=60.0
        )

        adapter.capture(_source())

        assert not orphan.exists()

    def test_a_reaper_failure_never_blocks_a_capture(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _boom_reap() -> NoReturn:
            raise OSError("simulated temp dir failure")

        monkeypatch.setattr(capture_module, "reap_orphaned_staged_files", _boom_reap)
        adapter = DockerPostgresqlCaptureAdapter(runner=_RecordingRunner(), store=_store(tmp_path))

        assert adapter.capture(_source()) is not None
