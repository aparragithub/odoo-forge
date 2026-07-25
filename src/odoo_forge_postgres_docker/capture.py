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

Staged temp file lifecycle has a SINGLE OWNER per stage: `_run_subprocess`
owns it until a `CaptureRunResult` exists, `capture()` owns it from there on.
There is no third, scattered cleanup site; each of those two functions
documents its own ownership window.

A SIGKILLed or OOM-killed parent runs no `finally` at all, so a best-effort
`reap_orphaned_staged_files()` sweep at the start of every `capture()` is the
backstop for staged files no live process owns anymore.

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
the other capture failure modes below without knowing the store's own error
taxonomy. If the compensating `discard` ALSO fails, both failures are chained
as the raised error's cause rather than one being swallowed silently.

Error taxonomy: six distinct `DatabaseOperationError` subclasses so callers
can tell apart six failure modes — a missing `docker` binary
(`CaptureBinaryUnavailableError`), a bounded timeout enforced by
`subprocess.run(..., timeout=)` (`CaptureTimeoutError`), a nonzero exit
(`CaptureCommandFailedError`), a rejected (unsafe) source identifier
(`InvalidCaptureIdentifierError`), a `StagedArtifactStore` persistence
failure (`CapturePersistenceError`), and a staging filesystem too small to
hold the dump (`CaptureStagingSpaceError`). This is a genuine subprocess-outcome
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
import shutil
import subprocess
import tempfile
import time
import uuid
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
# `pg_dump` for a real database can legitimately run for a long time, so the
# bound is generous by default. Callers with very large or very small sources
# should override it.
_DEFAULT_CAPTURE_TIMEOUT = 3600.0

_STAGED_FILE_PREFIX = "odoo-forge-capture-"
CAPTURE_APPLICATION_NAME_PREFIX = "odoo-forge-capture-"
_APPLICATION_NAME = re.compile(rf"^{re.escape(CAPTURE_APPLICATION_NAME_PREFIX)}[0-9a-f]{{1,64}}$")

# Free-space floor checked before a dump is streamed to `/tmp`. A constrained
# tmpfs filling mid-dump otherwise surfaces as a generic nonzero exit rather
# than a disk-exhaustion signal. The floor is a smoke alarm, not a capacity
# estimate: the final dump size is unknowable up front.
MIN_STAGING_FREE_BYTES = 1 << 28  # 256 MiB

# A staged temp file this old has no live owner: every in-flight capture holds
# its file for the duration of one bounded run, and the default bound is an
# hour. Anything older survived a SIGKILLed/OOM-killed parent.
ORPHAN_STAGED_FILE_MAX_AGE_SECONDS = 24 * 60 * 60

_REAP_TIMEOUT = 30.0


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


class CaptureStagingSpaceError(DatabaseOperationError):
    """The staging filesystem has too little free space to hold a captured dump."""

    public_detail = "insufficient free space to stage the captured dump"


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

# (container, application_name) -> None. Best-effort: implementations must never
# raise into the caller, and never replace the failure that triggered the reap.
BackendReaper = Callable[[str, str], None]


def new_capture_application_name() -> str:
    """Return a fresh `application_name` tag uniquely identifying one invocation."""
    return f"{CAPTURE_APPLICATION_NAME_PREFIX}{uuid.uuid4().hex}"


def terminate_in_container_backend(container: str, application_name: str) -> None:
    """Terminate the in-container Postgres backend serving one tagged invocation.

    Killing the local `docker exec` client does NOT reap the `pg_dump` process
    inside the container, nor the server-side backend it is streaming from, so
    a timed-out capture would otherwise leave a long-running query holding
    locks and a snapshot on the SOURCE database. Each capture tags its libpq
    connection with a unique `application_name`, so `pg_stat_activity` gives an
    exact, invocation-scoped handle: terminating that backend makes `pg_dump`
    itself exit.

    `psql` is used rather than `pkill`/`kill` because it is guaranteed present
    in a Postgres image (`procps` is not) and because it targets the backend by
    identity instead of by cmdline pattern. Entirely best-effort: any failure is
    swallowed so it never masks the `CaptureTimeoutError` that triggered it.
    """
    if _APPLICATION_NAME.fullmatch(application_name) is None:
        raise InvalidCaptureIdentifierError()
    statement = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE application_name = '{application_name}'"
    )
    with suppress(Exception):
        subprocess.run(  # noqa: S603 - argv-only, shell=False, never a shell string
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-tAc",
                statement,
            ],
            capture_output=True,
            check=False,
            shell=False,
            timeout=_REAP_TIMEOUT,
        )


def reap_orphaned_staged_files() -> None:
    """Remove staged capture temp files left behind by a killed parent process.

    `capture()`'s `try/finally` cleans the staged temp file on every path the
    interpreter survives — but a SIGKILL or an OOM kill runs no `finally`, so
    the file (potentially multi-GB) is orphaned in `/tmp` with no owner left.
    This sweep is the backstop: it reaps only files carrying this adapter's own
    `_STAGED_FILE_PREFIX` and only once they are older than
    `ORPHAN_STAGED_FILE_MAX_AGE_SECONDS`, so a concurrently running capture's
    in-flight file is never taken out from under it.
    """
    cutoff = time.time() - ORPHAN_STAGED_FILE_MAX_AGE_SECONDS
    for candidate in Path(tempfile.gettempdir()).glob(f"{_STAGED_FILE_PREFIX}*"):
        with suppress(OSError):
            if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)


def _require_staging_space() -> None:
    """Fail fast when the staging filesystem is too small to hold a dump.

    Advisory by design: if free space cannot be determined at all (an exotic
    or unreadable mount), the capture proceeds rather than being blocked by a
    diagnostic. The floor only converts the common, otherwise-opaque
    "constrained tmpfs fills mid-dump" case into a named error.
    """
    try:
        free = shutil.disk_usage(tempfile.gettempdir()).free
    except OSError:
        return
    if free < MIN_STAGING_FREE_BYTES:
        raise CaptureStagingSpaceError()


def _run_subprocess(argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
    """Run a capture subprocess into a staged temp file, hashing it back in bounded chunks.

    Delegates the bounded `timeout` entirely to `subprocess.run`, which the
    stdlib enforces via `communicate()`'s internal select/poll and KILLS the
    child (including a stalled producer that never writes any output) —
    unlike a hand-rolled read loop that only checks a deadline between
    blocking `read()` calls. The dump is written straight to a staged
    temporary file (never buffered in memory) and the digest is computed by
    reading that file back in bounded `_CHUNK_SIZE` chunks.

    This function is the SINGLE OWNER of the staged temp file until a
    `CaptureRunResult` exists for the caller to take ownership: ONE
    `try/except BaseException` spans the temp-file creation, the subprocess
    invocation, closing the file, AND the hash readback, so no failure on any
    of those steps can leak it. Two sequential guarded blocks would not be
    equivalent: `NamedTemporaryFile.__exit__` can itself raise (a failing
    `close()`, e.g. ENOSPC on flush) in the gap between them, and that gap
    belonged to no owner. `BaseException` rather than `Exception` because a
    `KeyboardInterrupt` during a multi-GB dump must still reclaim the space.

    The staged temp file is deliberately NOT removed on the success path
    (design D9, bridge slice B3): the caller
    (`DockerPostgresqlCaptureAdapter.capture`) hands it to a
    `StagedArtifactStore`, which moves it into durable custody.
    """
    argv_list = list(argv)
    _require_staging_space()
    staged_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=_STAGED_FILE_PREFIX, delete=False) as staged:
            staged_path = Path(staged.name)
            completed = subprocess.run(  # noqa: S603 - argv-only, shell=False, never a shell string
                argv_list,
                stdout=staged,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=timeout,
                check=False,
            )
        hasher = hashlib.sha256()
        with staged_path.open("rb") as readback:
            while chunk := readback.read(_CHUNK_SIZE):
                hasher.update(chunk)
    except BaseException:
        if staged_path is not None:
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
        reaper: BackendReaper = terminate_in_container_backend,
    ) -> None:
        self._store = store
        self._runner = runner
        self._timeout = timeout
        self._filestore_seam = filestore_seam
        self._reaper = reaper

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
        with suppress(Exception):
            reap_orphaned_staged_files()
        application_name = new_capture_application_name()
        argv = [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "postgres",
            "--format=custom",
            f"dbname={container} application_name={application_name}",
        ]
        staged_path: Path | None = None
        try:
            result = self._run(argv, container=container, application_name=application_name)
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
        except Exception as stage_failure:
            # The compensating discard is best-effort, but NOT silent: this module
            # has no logger, so a swallowed `discard` failure would leave a
            # persisted-but-unstaged manifest behind with no trace anywhere of why
            # compensation did not happen. Both failures are chained instead, so
            # the raised `CapturePersistenceError`'s `__cause__` carries the full
            # story to whatever does report it.
            compensation_failure: Exception | None = None
            try:
                self._store.discard(ref)
            except Exception as exc:
                compensation_failure = exc
            if compensation_failure is not None:
                raise CapturePersistenceError() from ExceptionGroup(
                    "capture staging failed and its compensating discard also failed",
                    [stage_failure, compensation_failure],
                )
            raise CapturePersistenceError() from stage_failure

    def _run(
        self, argv: Sequence[str], *, container: str, application_name: str
    ) -> CaptureRunResult:
        try:
            return self._runner(argv, timeout=self._timeout)
        except FileNotFoundError as exc:
            raise CaptureBinaryUnavailableError() from exc
        except subprocess.TimeoutExpired as exc:
            # `subprocess.run(..., timeout=)` already killed the LOCAL child (the
            # `docker exec` client), but that kill does not propagate into the
            # container: the in-container `pg_dump` and the source-side backend it
            # streams from keep running, holding a snapshot and locks. Reap that
            # one invocation by its unique `application_name` tag. Best-effort, so
            # a reaper failure never replaces the caller-meaningful timeout.
            with suppress(Exception):
                self._reaper(container, application_name)
            raise CaptureTimeoutError() from exc

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if _IDENTIFIER.fullmatch(value) is None:
            raise InvalidCaptureIdentifierError()


__all__ = [
    "CAPTURE_APPLICATION_NAME_PREFIX",
    "MIN_STAGING_FREE_BYTES",
    "ORPHAN_STAGED_FILE_MAX_AGE_SECONDS",
    "BackendReaper",
    "CaptureBinaryUnavailableError",
    "CaptureCommandFailedError",
    "CapturePersistenceError",
    "CaptureRunResult",
    "CaptureStagingSpaceError",
    "CaptureTimeoutError",
    "DockerCaptureRunner",
    "DockerPostgresqlCaptureAdapter",
    "FilestoreCaptureSeam",
    "InvalidCaptureIdentifierError",
    "emit_empty_filestore_component",
    "new_capture_application_name",
    "reap_orphaned_staged_files",
    "terminate_in_container_backend",
]
