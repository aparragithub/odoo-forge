"""Opt-in live composed `copy` CLI acceptance (WF-DATA-COPY closure).

Exercises the REAL registered Typer `copy` command against live Docker
PostgreSQL: real capture (`pg_dump`), real anonymization (scratch-database
`MaskTransform`), the real staged artifact store, and the real restore
(`pg_restore`) into a freshly provisioned target container -- through the
SAME composition root the CLI uses in production
(`odoo_forge_cli._composition._make_data_artifact_copy_coordinator`).

Run with `ODOO_FORGE_RUN_REAL_DOCKER=1`, matching the sibling opt-in
harnesses (`tests/odoo_forge_instances_postgres/test_real_postgres_process.py`,
`tests/adapters/test_postgres_docker_mask_transform_integration.py`).

Design (`sdd/WF-DATA-COPY/design`, corrected per #4362/#4365): a successful run
retains the delivered target through final SQL assertions, then harness
teardown removes it; a restore failure after real provisioning must instead
trigger provider rollback of the newly created target. Credentials are never
persisted: only `SopsCommandResolver.__call__` is patched to hand back one
runtime-generated password. No commit identity is recorded anywhere.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

import pytest
from typer.testing import CliRunner

from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge_cli import _composition
from odoo_forge_cli.main import app
from odoo_forge_docker.credential_injection import SopsCommandResolver
from odoo_forge_postgres_docker.capture import emit_empty_filestore_component
from odoo_forge_postgres_docker.restore_target import RestoreByteSource, make_docker_restore_target
from odoo_forge_postgres_docker.staged_capability import make_staged_byte_source
from odoo_forge_postgres_docker.staged_store import (
    FilesystemStagedArtifactStore,
    StagedArtifactUnavailableError,
)

pytestmark = [pytest.mark.integration, pytest.mark.real_docker]

_SCRATCH_NAME_FILTER = "odoo-forge-mask-scratch-"

_IMAGE = "postgres:16"
_TABLE = "res_partner"
_RUNTIME_PASSWORD = "wf-data-copy-acceptance-runtime-password"  # nosec - throwaway, never persisted


def _docker(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 - test harness, argv-only
        ["docker", *argv], capture_output=True, check=False
    )


def _require_real_docker() -> None:
    """Skip only when the explicitly requested live prerequisites are absent."""
    if os.environ.get("ODOO_FORGE_RUN_REAL_DOCKER") != "1":
        pytest.skip("real Docker acceptance disabled; set ODOO_FORGE_RUN_REAL_DOCKER=1")
    if shutil.which("docker") is None:
        pytest.skip("Docker prerequisite unavailable: executable not found")
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("Docker prerequisite unavailable: daemon probe timed out after 5s")
    else:
        if result.returncode != 0:
            pytest.skip("Docker prerequisite unavailable: daemon is unreachable")


def _run_token() -> str:
    return uuid.uuid4().hex[:12]


def _wait_for_database(container: str) -> None:
    """Poll a REAL query, not `pg_isready`: the postgres entrypoint runs a
    temporary bootstrap server during initdb, so `pg_isready` reports ready
    before the named database actually exists."""
    for _ in range(120):
        probe = _docker(
            ["exec", container, "psql", "-U", "postgres", "-d", container, "-tAc", "SELECT 1"]
        )
        if probe.returncode == 0:
            return
        time.sleep(0.25)
    pytest.fail(f"database {container} never became reachable in {container}")


def _sql(container: str, statement: str) -> str:
    result = _docker(
        [
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            container,
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            statement,
        ]
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout.decode().strip()


def _container_exists(name: str) -> bool:
    return _docker(["inspect", name]).returncode == 0


def _scratch_container_names() -> set[str]:
    """Snapshot every live-or-dead `MaskTransform` scratch container name.

    Names are `odoo-forge-mask-scratch-{uuid4().hex}` (unrelated to this
    harness's run token), so a before/after snapshot delta — not a
    token-scoped filter — is what proves the mask round trip's OWN scratch
    container never leaks past a run (spec R2: "owned temporary capture,
    scratch, staged, and disposable target resources are absent").
    """
    result = _docker(
        ["ps", "-a", "--filter", f"name={_SCRATCH_NAME_FILTER}", "--format", "{{.Names}}"]
    )
    return {line for line in result.stdout.decode().splitlines() if line}


@contextmanager
def _sentinel_container(name: str) -> Iterator[str]:
    """A container that pre-EXISTS the `copy` invocation and is UNRELATED to
    it (never the source, target, or any owned/scratch resource).

    Proves the selective half of spec R2 ("AND pre-existing or unowned
    resources remain available" / "AND unrelated resources are not
    removed") — without this, a cleanup/rollback bug that deletes
    EVERYTHING would pass every other assertion in this module, since
    nothing here previously proved survival, only removal.
    """
    started = _docker(
        ["run", "--detach", "--name", name, "--network", "none", _IMAGE, "sleep", "infinity"]
    )
    assert started.returncode == 0, started.stderr.decode()
    try:
        yield name
    finally:
        _docker(["rm", "-f", name])


def _plant_sentinel_staged_artifact(
    tmp_path: Path, store_root: Path, token: str
) -> tuple[FilesystemStagedArtifactStore, DataArtifactRef, RestoreSetComponent]:
    """Plant one pre-existing staged manifest+blob under a ref UNRELATED to
    this run's own operation ref (`restore-set-<source>`).

    `FilesystemStagedArtifactStore.discard` only ever unlinks a component's
    blob when NO OTHER staged manifest still references its digest, so a
    manifest under a completely different ref is never touched by this
    run's own success-path discard (D12) or failure-path compensation
    (`DataArtifactCopyCoordinator._compensate`) — the same real production
    invariant this test now exercises rather than assumes.
    """
    # `FilesystemStagedArtifactStore._ensure_root` only ever creates ITS OWN
    # root directory (no `parents=True`); in production the sibling
    # `LocalOwnershipAuthority` default root creates the shared
    # `$XDG_STATE_HOME/odoo-forge` parent first as a side effect. Planting a
    # sentinel BEFORE `copy` runs cannot rely on that side effect happening
    # first, so this creates the parent hierarchy explicitly.
    store_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = FilesystemStagedArtifactStore(store_root)
    sentinel_bytes = f"sentinel-payload-{token}".encode()
    digest = ArtifactDigest(algorithm="sha256", value=hashlib.sha256(sentinel_bytes).hexdigest())
    sentinel_source_path = tmp_path / f"sentinel-{token}.bin"
    sentinel_source_path.write_bytes(sentinel_bytes)
    store.stage(digest, sentinel_source_path)
    database_component = RestoreSetComponent(
        kind=ArtifactComponentKind.DATABASE,
        opaque_component_ref=f"database-sentinel-{token}",
        format_version="pg_dump-custom-v1",
        digest=digest,
    )
    manifest = RestoreSetManifest(
        restore_set_id=f"sentinel-{token}",
        lineage_id=f"sentinel-lineage-{token}",
        components=(database_component, emit_empty_filestore_component()),
    )
    ref = DataArtifactRef(f"sentinel-{token}")
    store.put(ref, manifest)
    return store, ref, database_component


def _assert_sentinel_staged_artifact_survives(
    store: FilesystemStagedArtifactStore, ref: DataArtifactRef, component: RestoreSetComponent
) -> Path:
    """Real survival proof: re-resolve the sentinel manifest AND re-open its
    blob. `open_component` recomputes the blob's SHA-256 and compares it
    against `component.digest`, raising `StagedArtifactIntegrityError` on any
    mismatch and `StagedArtifactUnavailableError` if the blob is gone — so a
    clean return here is proof the sentinel bytes are UNCHANGED and present,
    not merely that some file exists. Returns the blob path so callers can
    also assert it is the ONLY thing left in the blobs directory."""
    manifest = store.resolve(ref)
    assert manifest.restore_set_id == str(ref)
    survived_blob_path = store.open_component(component)
    assert survived_blob_path.stat().st_size > 0
    return survived_blob_path


_SEED_SCHEMA = f"""
CREATE TABLE {_TABLE} (id serial PRIMARY KEY, email text, city text);
INSERT INTO {_TABLE} (email, city) VALUES
    ('ada@example.test', 'Madrid'),
    ('alan@example.test', 'Rosario');
"""


@contextmanager
def _source_container(name: str) -> Iterator[str]:
    """A source container whose own name IS its database name.

    `DockerPostgresqlCaptureAdapter.capture` runs `pg_dump ... dbname={container}`
    (design: "Custom source container whose database name equals its
    container name"), so the seeded database MUST be named after the
    container itself.
    """
    started = _docker(
        [
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            "none",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            f"POSTGRES_DB={name}",
            _IMAGE,
        ]
    )
    assert started.returncode == 0, started.stderr.decode()
    try:
        _wait_for_database(name)
        _sql(name, _SEED_SCHEMA)
        yield name
    finally:
        _docker(["rm", "-f", name])


def _patch_runtime_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Design: patch ONLY `SopsCommandResolver.__call__` to return one
    runtime-generated password; it is never persisted or logged."""
    monkeypatch.setattr(SopsCommandResolver, "__call__", lambda self, handle: _RUNTIME_PASSWORD)


def _isolate_staged_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path / "odoo-forge" / "artifact-store"


def test_copy_composes_capture_anonymize_stage_restore_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requirement: Prove one composed source-to-target database copy.

    Exercises the real composed `copy` path end to end: capture succeeds,
    the configured sensitive column is masked, the control column survives
    unchanged, staged bytes are observed (real digest, non-empty) before the
    real restore runs, and the retained target contains the expected rows.
    """
    _require_real_docker()
    store_root = _isolate_staged_store(tmp_path, monkeypatch)
    _patch_runtime_password(monkeypatch)

    observed_pre_restore: dict[str, str] = {}
    observed_byte_lengths: dict[str, int] = {}

    def _observing_make_staged_byte_source(store: StagedArtifactStore) -> RestoreByteSource:
        """Delegating pre-restore hook: observe the real staged bytes, their
        real byte length, and their digest right before the real
        `RestoreTarget` streams them, without changing the default
        success-cleanup behavior. Recording the byte length separately
        matters: a 64-hex-char SHA-256 digest alone does not prove
        non-emptiness (`sha256(b"")` is also 64 hex characters), so this
        harness never claims non-emptiness from digest shape alone."""
        real_byte_source = make_staged_byte_source(store)

        def _byte_source(component: RestoreSetComponent) -> Path:
            path = real_byte_source(component)
            contents = path.read_bytes()
            observed_pre_restore["digest"] = hashlib.sha256(contents).hexdigest()
            observed_byte_lengths["value"] = len(contents)
            return path

        return _byte_source

    monkeypatch.setattr(_composition, "make_staged_byte_source", _observing_make_staged_byte_source)

    token = _run_token()
    source_name = f"odoo-forge-copyacc-src-{token}"
    target = f"odoo-forge-copyacc-tgt-{token}"
    sentinel_name = f"odoo-forge-copyacc-sentinel-{token}"
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        f"version: 1\nrules:\n  - table: {_TABLE}\n    column: email\n    mask_strategy: hash\n"
    )

    # Plant BOTH kinds of pre-existing, UNRELATED resources before invoking
    # `copy`, so cleanup can be proven SELECTIVE (spec R2), not just
    # "something got removed".
    sentinel_store, sentinel_ref, sentinel_component = _plant_sentinel_staged_artifact(
        tmp_path, store_root, token
    )
    scratch_before = _scratch_container_names()

    runner = CliRunner()
    try:
        with _sentinel_container(sentinel_name), _source_container(source_name) as source:
            result = runner.invoke(
                app,
                [
                    "copy",
                    source,
                    target,
                    "--credentials-file",
                    str(tmp_path / "unused-credentials.sops.yaml"),
                    "--anonymization-policy-file",
                    str(policy_file),
                ],
            )

            assert result.exit_code == 0, result.output
            assert "1 rule(s) applied" in result.output
            assert "Traceback" not in result.output
            assert _RUNTIME_PASSWORD not in result.output
            assert "ada@example.test" not in result.output
            assert "alan@example.test" not in result.output

            # Durable staged artifact and integrity: the real byte source resolved
            # a real staged blob and hashed it right before restore. Byte
            # length and digest shape are asserted SEPARATELY: a 64-hex-char
            # digest alone would also match `sha256(b"")`.
            assert observed_byte_lengths.get("value", 0) > 0, "staged blob must be non-empty"
            assert len(observed_pre_restore.get("digest", "")) == 64

            # Restore and final target assertions: the retained target is
            # reachable and contains masked sensitive data plus an untouched
            # control column.
            _wait_for_database(target)
            emails = _sql(target, f"SELECT email FROM {_TABLE} ORDER BY id")
            cities = _sql(target, f"SELECT city FROM {_TABLE} ORDER BY id")
            row_count = _sql(target, f"SELECT count(*) FROM {_TABLE}")
            assert row_count == "2", "restore must not drop or duplicate rows"
            assert "ada@example.test" not in emails
            assert "alan@example.test" not in emails
            assert emails.split("\n") == [
                hashlib.md5(b"ada@example.test").hexdigest(),  # noqa: S324 - asserting md5()
                hashlib.md5(b"alan@example.test").hexdigest(),  # noqa: S324
            ], "HASH must be deterministic md5 of the original value"
            assert cities.split("\n") == ["Madrid", "Rosario"], "control survives unmasked"

            # Sentinel container: proves cleanup did NOT remove an unrelated,
            # pre-existing resource ("AND pre-existing or unowned resources
            # remain available").
            assert _container_exists(sentinel_name)

            # Sentinel staged artifact: proves discard-on-success only ever
            # touched THIS run's own ref, never an unrelated one.
            sentinel_blob_path = _assert_sentinel_staged_artifact_survives(
                sentinel_store, sentinel_ref, sentinel_component
            )

            # Successful cleanup: workflow discard-on-success (retain_staged=False,
            # the CLI default) must leave no residual staged blobs from THIS
            # run's own operation — the ONLY blob left must be the
            # pre-existing sentinel planted above, never zero-and-never-more.
            blobs_dir = store_root / "blobs"
            residual_blobs = set(blobs_dir.iterdir()) if blobs_dir.exists() else set()
            assert residual_blobs == {sentinel_blob_path}, (
                f"only the pre-existing sentinel blob may remain after success discard, "
                f"got: {residual_blobs}"
            )

            # Scratch database absence: the mask round trip's OWN throwaway
            # scratch container (`odoo-forge-mask-scratch-*`) must never
            # leak past a successful run.
            assert _scratch_container_names() == scratch_before, (
                "mask-transform scratch container must not leak after success"
            )
    finally:
        # Harness teardown removes the retained target only AFTER the final
        # assertions above ran against it; a leak-safe backstop, exact-name
        # only.
        _docker(["rm", "-f", target])


def test_copy_rolls_back_the_newly_provisioned_target_after_a_restore_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requirement: Prove ownership-safe lifecycle behavior (failure rollback).

    Injects one narrow post-provision restore failure (real target container
    is really provisioned, then the restore step is forced to fail) and
    asserts the provider's own rollback removes the newly created target,
    without a raw traceback ever reaching CLI output.
    """
    _require_real_docker()
    store_root = _isolate_staged_store(tmp_path, monkeypatch)
    _patch_runtime_password(monkeypatch)

    def _failing_runner(
        argv: object, *, stdin: IO[bytes], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        stdin.read()
        return subprocess.CompletedProcess(
            list(argv) if isinstance(argv, list) else [], returncode=1, stdout="", stderr="injected"
        )

    def _failing_restore_target(*, byte_source: Callable[[object], Path]) -> Callable[..., bool]:
        return make_docker_restore_target(byte_source=byte_source, runner=_failing_runner)

    monkeypatch.setattr(_composition, "make_docker_restore_target", _failing_restore_target)

    token = _run_token()
    source_name = f"odoo-forge-copyacc-src-{token}"
    target = f"odoo-forge-copyacc-fail-{token}"
    sentinel_name = f"odoo-forge-copyacc-fail-sentinel-{token}"

    sentinel_store, sentinel_ref, sentinel_component = _plant_sentinel_staged_artifact(
        tmp_path, store_root, token
    )

    runner = CliRunner()
    try:
        with _sentinel_container(sentinel_name), _source_container(source_name) as source:
            result = runner.invoke(
                app,
                [
                    "copy",
                    source,
                    target,
                    "--credentials-file",
                    str(tmp_path / "unused-credentials.sops.yaml"),
                ],
            )

            assert result.exit_code == 1
            assert "error:" in result.output
            assert "Traceback" not in result.output
            assert _RUNTIME_PASSWORD not in result.output
            # Provider rollback removed the newly provisioned target; no leak.
            assert not _container_exists(target)

            # Sentinel container: unrelated pre-existing resource must survive
            # a FAILED run just as much as a successful one ("AND unrelated
            # resources are not removed").
            assert _container_exists(sentinel_name)

            # Sentinel staged artifact: rollback compensation must only ever
            # discard THIS run's own ref, never an unrelated one.
            _assert_sentinel_staged_artifact_survives(
                sentinel_store, sentinel_ref, sentinel_component
            )

            # No restorable raw delivery state: this run's OWN captured
            # manifest ref must be gone after compensation, so a retry could
            # never accidentally restore the un-anonymized raw capture from a
            # half-finished operation. Asserting "the whole store is empty"
            # would be wrong now that a sentinel legitimately remains; this
            # asserts the SPECIFIC owned ref is gone instead.
            own_ref = DataArtifactRef(f"restore-set-{source_name}")
            with pytest.raises(StagedArtifactUnavailableError):
                sentinel_store.resolve(own_ref)
    finally:
        _docker(["rm", "-f", target])
