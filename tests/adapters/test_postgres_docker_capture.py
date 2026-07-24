"""RED-first tests for the Docker-backed Postgres capture adapter."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import IO, NoReturn, cast

import pytest

from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_artifacts.contracts import ArtifactComponentKind
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge_postgres_docker.capture import (
    CaptureBinaryUnavailableError,
    CaptureCommandFailedError,
    CapturePersistenceError,
    CaptureRunResult,
    CaptureTimeoutError,
    DockerPostgresqlCaptureAdapter,
    InvalidCaptureIdentifierError,
)
from odoo_forge_postgres_docker.staged_store import FilesystemStagedArtifactStore

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


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

    assert runner.calls == [
        [
            "docker",
            "exec",
            "odoo-source",
            "pg_dump",
            "-U",
            "postgres",
            "--format=custom",
            "odoo-source",
        ]
    ]
    for argv in runner.calls:
        assert isinstance(argv, list)
        assert all(isinstance(item, str) for item in argv)

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
    chunks = [b"chunk-one-", b"chunk-two-", b"chunk-three"]
    full = b"".join(chunks)

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        stdout = cast("IO[bytes]", kwargs["stdout"])
        for chunk in chunks:
            stdout.write(chunk)
        stdout.flush()
        return subprocess.CompletedProcess(list(argv), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter(store=_store(tmp_path))

    manifest = adapter.capture(_source())

    database = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert database.digest.value == hashlib.sha256(full).hexdigest()


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
