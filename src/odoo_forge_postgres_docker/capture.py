"""Docker-backed capture adapter producing a raw restore set manifest from a live source.

Runs `pg_dump` argv-only (`shell=False`), never through a shell, and rejects
any source identifier that does not match the safe container/database
identifier shape (`_IDENTIFIER`). The `ArtifactDigest` is computed from the
captured bytes BEFORE `capture()` returns (never deferred to delivery time,
per spec) — but, unlike a naive `subprocess.run(capture_output=True)`, the
dump is streamed to a staged temporary file and hashed back in bounded chunks
(`_CHUNK_SIZE`) so a multi-GB dump is never held fully in memory. On failure
the temporary file is always removed; on success it is moved into durable
custody (see "Capture persistence" below) rather than deleted.

The filestore component is a pass-through seam (`FilestoreCaptureSeam`) that
emits a deterministic, zero-content component with `format_version="empty-v1"`
until a real filestore capture adapter exists; the manifest shape and validator
(exactly one database + one filestore component) require no change when that
adapter is composed in later (D6).

Anonymization decisions are explicitly OUT of scope here (D4): this adapter
always returns the RAW, un-anonymized manifest.

Capture persistence (design D9, bridge slice B3): the captured dump is no
longer deleted once hashed. Instead, `capture()` hands the staged temp file to
an injected `StagedArtifactStore`, which moves it into durable, content-
addressed custody keyed by its digest, and persists the manifest under
`manifest.restore_set_id`.

Staged temp file lifecycle has a SINGLE OWNER per stage, mechanically
verifiable: (1) while the staged temp file is only visible to the runner
itself (`_run_subprocess`, the default `DockerCaptureRunner`), a single
`try/except` spanning BOTH the subprocess invocation and the bounded hash
readback unlinks it on any failure before a `CaptureRunResult` ever exists —
this closes a leak window a naive split (subprocess-only cleanup, readback
unguarded) would otherwise leave open; (2) from the moment `capture()` obtains
a `CaptureRunResult` onward — through a nonzero-exit check, manifest
construction, and persistence — `capture()` itself owns the staged path in
one `try/finally` that unconditionally unlinks it at the end (a no-op once the
store has moved it into custody). There is no third, scattered cleanup site.

Persistence order is deliberately `store.put(ref, manifest)` BEFORE
`store.stage(digest, staged_path)` (not the reverse): if `put` fails, no blob
was ever moved into custody, so there is nothing to orphan and `capture()`'s
`finally` cleans the still-unmoved temp file. If `stage` fails after `put`
succeeded, the persisted-but-unstaged manifest is compensated with a
best-effort `store.discard(ref)` — the existing `StagedArtifactStore.discard`
contract already resolves the manifest and reaps its (in this case
never-staged) blob, so no new store API surface is needed. Both `put` and
`stage` failures are re-raised as `CapturePersistenceError`, never as a raw
`StagedArtifactError`, so callers can discriminate persistence failures from
the other four capture failure modes below without knowing the store's own
error taxonomy.

Error taxonomy: five distinct `DatabaseOperationError` subclasses so callers
can tell apart five failure modes — a missing `docker` binary
(`CaptureBinaryUnavailableError`), a bounded timeout enforced by
`subprocess.run(..., timeout=)` (`CaptureTimeoutError`), a nonzero exit
(`CaptureCommandFailedError`), a rejected (unsafe) source identifier
(`InvalidCaptureIdentifierError`), and a `StagedArtifactStore` persistence
failure (`CapturePersistenceError`). This is a genuine subprocess-outcome
split plus identifier validation and persistence-boundary mapping for THIS
adapter's own needs; it is not a claim of exact parity with `provider.py`'s
narrower two-error split. Every error carries only a fixed, redacted-safe
`public_detail` — never raw stderr, argv, store diagnostics, or connection
material — matching `DatabaseOperationError`'s existing redaction contract.

Filestore component note: the manifest's filestore component
(`emit_empty_filestore_component`) is metadata-only — a deterministic,
zero-content placeholder (`format_version="empty-v1"`) with no corresponding
blob ever staged in the store (design D6/D8). Callers must never call
`store.open_component(filestore_component)` for it; only the DATABASE
component resolves real staged bytes. A real filestore capture adapter
composed in later will replace `emit_empty_filestore_component` and is
expected to stage real bytes for its component at that point.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import DatabaseOperationError

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_CHUNK_SIZE = 1 << 20  # 1 MiB: bounds in-memory buffering of a streamed dump.
# `pg_dump` for a real database can legitimately run for a long time; 30s (the
# original default) was unrealistic for anything beyond a tiny test fixture.
# Callers with very large or very small sources should override this.
_DEFAULT_CAPTURE_TIMEOUT = 3600.0


class CaptureBinaryUnavailableError(DatabaseOperationError):
    """The `docker` binary required to run the capture command is unavailable."""

    public_detail = "capture command binary is unavailable"


class CaptureTimeoutError(DatabaseOperationError):
    """A capture subprocess invocation did not complete within its bounded timeout."""

    public_detail = "capture operation timed out"


class CaptureCommandFailedError(DatabaseOperationError):
    """A capture subprocess invocation returned a nonzero exit status."""

    public_detail = "capture command failed"


class InvalidCaptureIdentifierError(DatabaseOperationError):
    """A source identifier does not match the safe container/database shape."""

    public_detail = "capture source identifier is invalid"


class CapturePersistenceError(DatabaseOperationError):
    """A `StagedArtifactStore` failure occurred while persisting a capture."""

    public_detail = "capture persistence failed"


@dataclass(frozen=True)
class CaptureRunResult:
    """The outcome of one streamed capture subprocess invocation.

    `digest_hex` is always computed incrementally, in bounded chunks, over the
    captured stdout stream — never from a fully materialized in-memory buffer.
    `staged_path` is the temp file the dump was streamed into; the caller
    (`DockerPostgresqlCaptureAdapter.capture`) is responsible for moving it
    into durable custody (design D9) or removing it on failure — this result
    never deletes it itself.
    """

    returncode: int
    digest_hex: str
    staged_path: Path


class DockerCaptureRunner(Protocol):
    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult: ...


FilestoreCaptureSeam = Callable[[], RestoreSetComponent]


def _run_subprocess(argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
    """Run a capture subprocess into a staged temp file, hashing it back in bounded chunks.

    Delegates the bounded `timeout` entirely to `subprocess.run`, which the
    stdlib enforces via `communicate()`'s internal select/poll and KILLS the
    child (including a stalled producer that never writes any output) —
    unlike a hand-rolled read loop that only checks a deadline between
    blocking `read()` calls. The dump is written straight to a staged
    temporary file (never buffered in memory) and the digest is computed by
    reading that file back in bounded `_CHUNK_SIZE` chunks.

    This function is the SINGLE OWNER of the staged temp file for as long as
    it is the only place holding a reference to it (before a
    `CaptureRunResult` exists for the caller to take over cleanup): both the
    subprocess invocation AND the hash readback are covered by the SAME
    failure handling, so a readback failure (e.g. I/O error, ENOSPC) can never
    leak the temp file the way an except-around-subprocess-only split would.
    The staged temp file is deliberately NOT removed on the success path
    (design D9, bridge slice B3): the caller
    (`DockerPostgresqlCaptureAdapter.capture`) hands it to a
    `StagedArtifactStore`, which moves it into durable custody.
    """
    argv_list = list(argv)
    with tempfile.NamedTemporaryFile(prefix="odoo-forge-capture-", delete=False) as staged:
        staged_path = Path(staged.name)
        try:
            completed = subprocess.run(  # noqa: S603 - argv-only, shell=False, never a shell string
                argv_list,
                stdout=staged,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=timeout,
                check=False,
            )
        except Exception:
            staged_path.unlink(missing_ok=True)
            raise
    try:
        hasher = hashlib.sha256()
        with staged_path.open("rb") as readback:
            while chunk := readback.read(_CHUNK_SIZE):
                hasher.update(chunk)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise
    return CaptureRunResult(
        returncode=completed.returncode, digest_hex=hasher.hexdigest(), staged_path=staged_path
    )


def emit_empty_filestore_component() -> RestoreSetComponent:
    """Return the deterministic, zero-content filestore pass-through component."""
    return RestoreSetComponent(
        kind=ArtifactComponentKind.FILESTORE,
        opaque_component_ref="filestore-empty-v1",
        format_version="empty-v1",
        digest=ArtifactDigest(algorithm="sha256", value=_EMPTY_SHA256),
    )


class DockerPostgresqlCaptureAdapter:
    """Captures a live Postgres source into a raw (un-anonymized) restore set manifest."""

    def __init__(
        self,
        *,
        store: StagedArtifactStore,
        runner: DockerCaptureRunner = _run_subprocess,
        timeout: float = _DEFAULT_CAPTURE_TIMEOUT,
        filestore_seam: FilestoreCaptureSeam = emit_empty_filestore_component,
    ) -> None:
        self._store = store
        self._runner = runner
        self._timeout = timeout
        self._filestore_seam = filestore_seam

    def capture(self, source: CaptureSource) -> RestoreSetManifest:
        """Capture a source into a persisted restore set manifest (design D9).

        The staged temp file has a SINGLE OWNER from here until it is moved
        into the store: this method wraps the whole "obtain dump -> hash ->
        build manifest -> persist" flow in one `try/finally` that
        unconditionally unlinks the staged path at the end (a no-op once
        `_persist` has moved it into custody). This is the only place, beyond
        `_run_subprocess`'s own narrower ownership window, that ever touches
        the staged path — there is no third, scattered cleanup site.
        """
        container = source.target.target_id
        self._validate_identifier(container)
        argv = [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "postgres",
            "--format=custom",
            container,
        ]
        staged_path: Path | None = None
        try:
            result = self._run(argv)
            staged_path = result.staged_path
            if result.returncode != 0:
                raise CaptureCommandFailedError()
            digest = ArtifactDigest(algorithm="sha256", value=result.digest_hex)
            database_component = RestoreSetComponent(
                kind=ArtifactComponentKind.DATABASE,
                opaque_component_ref=f"database-{container}",
                format_version="pg_dump-custom-v1",
                digest=digest,
            )
            manifest = RestoreSetManifest(
                restore_set_id=f"restore-set-{container}",
                lineage_id=f"lineage-{container}",
                components=(database_component, self._filestore_seam()),
            )
            self._persist(digest, staged_path, manifest)
        finally:
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)
        return manifest

    def _persist(
        self, digest: ArtifactDigest, staged_path: Path, manifest: RestoreSetManifest
    ) -> None:
        """Persist `manifest` then move the staged dump into durable custody (design D9).

        `put` runs BEFORE `stage` deliberately: if `put` fails, no blob was
        ever moved into custody, so there is nothing to orphan (the caller's
        `finally` cleans the still-unmoved staged temp file). If `stage` fails
        after `put` succeeded, the persisted-but-unstaged manifest is
        compensated with a best-effort `store.discard(ref)` — reusing the
        existing `discard(ref)` contract instead of adding a new store API
        surface. Both failures are re-raised as `CapturePersistenceError`,
        never as a raw `StagedArtifactError`.
        """
        ref = DataArtifactRef(manifest.restore_set_id)
        try:
            self._store.put(ref, manifest)
        except Exception as exc:
            raise CapturePersistenceError() from exc
        try:
            self._store.stage(digest, staged_path)
        except Exception as exc:
            with suppress(Exception):
                self._store.discard(ref)
            raise CapturePersistenceError() from exc

    def _run(self, argv: Sequence[str]) -> CaptureRunResult:
        try:
            return self._runner(argv, timeout=self._timeout)
        except FileNotFoundError as exc:
            raise CaptureBinaryUnavailableError() from exc
        except subprocess.TimeoutExpired as exc:
            # `subprocess.run(..., timeout=)` already killed the child process
            # (including a stalled producer that never wrote any output), so
            # there is no orphan to clean up here.
            raise CaptureTimeoutError() from exc

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if _IDENTIFIER.fullmatch(value) is None:
            raise InvalidCaptureIdentifierError()


__all__ = [
    "CaptureBinaryUnavailableError",
    "CaptureCommandFailedError",
    "CapturePersistenceError",
    "CaptureRunResult",
    "CaptureTimeoutError",
    "DockerCaptureRunner",
    "DockerPostgresqlCaptureAdapter",
    "FilestoreCaptureSeam",
    "InvalidCaptureIdentifierError",
    "emit_empty_filestore_component",
]
