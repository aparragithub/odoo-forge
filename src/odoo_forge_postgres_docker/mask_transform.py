"""Real byte-level `MaskTransform`: anonymize a captured dump via a scratch-DB round trip.

`odoo_forge.anonymization.apply` owns the PURE step (which manifest component
gets masked, and what evidence that produces) and delegates the bytes to an
injected `MaskTransform` port. This module is that port's Postgres/Docker
implementation — the adapter half of the same pure-step/adapter split as
`credentials/materialization.py`.

Why a scratch database and not a byte rewrite: capture produces
`pg_dump --format=custom`, a compressed, indexed archive. Its rows are not
addressable as bytes, so "mask the dump in place" is not a thing that exists.
The archive must be interpreted by Postgres to be modified. So masking:

  1. streams the staged raw dump into a THROWAWAY container via `pg_restore`
  2. applies exactly one `UPDATE` per `AnonymizationRule` there
  3. re-dumps with `pg_dump --format=custom` — same archive format in, same out
  4. stages those masked bytes under their own digest and returns a component
     pointing at them

The ordering is the whole point of the design: the raw bytes are only ever
interpreted inside a container that is destroyed before this function returns,
so the DELIVERY TARGET never sees un-anonymized data. Masking after restoring
into the target would be simpler and would also mean shipping the raw data to
the target first, which is precisely what anonymize-before-delivery forbids.
The scratch container is torn down in a `finally`, on success and on every
failure path, because until it is gone it holds the raw PII.

Fail-closed everywhere: an `UPDATE` that cannot be applied (missing table or
column) aborts the whole transform via `ON_ERROR_STOP=1` plus a nonzero-exit
check. A dump stamped `anonymization_applied` with one rule silently skipped
is worse than a failed copy.

An EMPTY rule set returns the component untouched rather than round-tripping.
`pg_dump` is not byte-stable, so a no-op round trip would churn the digest and
spin up a container holding raw PII to accomplish nothing.

Injection safety: `AnonymizationRule.table`/`column` are already constrained to
`[A-Za-z0-9_-]+` by `require_safe_opaque_identifier`, but `-` is subtraction in
an unquoted SQL identifier, so identifiers are double-quoted — and since the
selector charset cannot contain `"`, quoting cannot be escaped out of.
`static_value` is the only free-form field a rule carries and is NOT covered by
that charset, so its single quotes are doubled per SQL literal rules. Every
subprocess is argv-only with `shell=False`; no statement is ever assembled by
a shell.

Error taxonomy mirrors `capture.py`'s `Capture*` and `restore_target.py`'s
`Restore*` conventions, so the three adapters read the same way.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from odoo_forge.anonymization.policy import AnonymizationRule, MaskStrategy
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.database.errors import DatabaseOperationError

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_CHUNK_SIZE = 1 << 20  # 1 MiB, matching capture.py: bounds the re-dump hash readback.
_STAGED_FILE_PREFIX = "odoo-forge-mask-"
_SCRATCH_NAME_PREFIX = "odoo-forge-mask-"

_DEFAULT_MASK_TIMEOUT = 3600.0
_DEFAULT_SCRATCH_IMAGE = "postgres:16"
_DEFAULT_SCRATCH_DATABASE = "maskdb"
_READINESS_ATTEMPTS = 60
_READINESS_INTERVAL_SECONDS = 1.0
_SCRATCH_COMMAND_TIMEOUT = 120.0

_REDACTED_MARKER = "[REDACTED]"


class MaskBinaryUnavailableError(DatabaseOperationError):
    """The `docker` binary required to run the masking round trip is unavailable."""

    public_detail = "masking command binary is unavailable"


class MaskTimeoutError(DatabaseOperationError):
    """A masking subprocess invocation did not complete within its bounded timeout."""

    public_detail = "masking operation timed out"


class MaskCommandFailedError(DatabaseOperationError):
    """A masking subprocess invocation returned a nonzero exit status."""

    public_detail = "masking command failed"


class InvalidMaskSelectorError(DatabaseOperationError):
    """A rule selector does not match the safe SQL identifier shape."""

    public_detail = "anonymization selector is invalid"


class MaskScratchUnavailableError(DatabaseOperationError):
    """The throwaway masking database could not be started or never became ready."""

    public_detail = "scratch masking database is unavailable"


class MaskPersistenceError(DatabaseOperationError):
    """A `StagedArtifactStore` failure occurred while persisting masked bytes."""

    public_detail = "masked artifact persistence failed"


@dataclass(frozen=True)
class ScratchDatabase:
    """A live, throwaway Postgres database the raw dump may be restored into."""

    container: str
    database: str


class DockerMaskRunner(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: IO[bytes] | None = None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]: ...


# A context manager yielding a ready scratch database and destroying it on exit.
ScratchDatabaseFactory = Callable[[], AbstractContextManager[ScratchDatabase]]


def _run_mask_subprocess(
    argv: Sequence[str],
    *,
    stdin: IO[bytes] | None = None,
    stdout: IO[bytes] | None = None,
    timeout: float,
) -> subprocess.CompletedProcess[bytes]:
    """Run one scratch-container command, streaming through files rather than memory.

    `stdin`/`stdout` are open file objects so a multi-GB dump moves between disk
    and the subprocess without ever being buffered whole, matching `capture.py`
    and `restore_target.py`. `timeout` is delegated to `subprocess.run`, which
    kills a stalled child itself.
    """
    return subprocess.run(  # noqa: S603 - argv-only, shell=False, never a shell string
        list(argv),
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.DEVNULL,
        check=False,
        shell=False,
        timeout=timeout,
    )


@contextmanager
def docker_scratch_database(
    *,
    image: str = _DEFAULT_SCRATCH_IMAGE,
    database: str = _DEFAULT_SCRATCH_DATABASE,
    readiness_attempts: int = _READINESS_ATTEMPTS,
) -> Iterator[ScratchDatabase]:
    """Start a throwaway Postgres container, yield it, and always destroy it.

    The container is named rather than referenced by id so every argv stays
    within the safe identifier shape the sibling adapters validate. It is
    started with no published ports and reached only through `docker exec`, so
    the raw data restored into it is never exposed on the network.

    `docker rm -f` runs in a `finally` covering the readiness wait as well as
    the body: a container that never became ready may still have started, and
    while it exists it may hold raw, un-anonymized data.
    """
    container = f"{_SCRATCH_NAME_PREFIX}{uuid.uuid4().hex}"
    _run_mask_subprocess(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            container,
            "--env",
            "POSTGRES_PASSWORD=scratch",
            "--env",
            f"POSTGRES_DB={database}",
            image,
        ],
        timeout=_SCRATCH_COMMAND_TIMEOUT,
    )
    try:
        _await_scratch_readiness(container, database, attempts=readiness_attempts)
        yield ScratchDatabase(container=container, database=database)
    finally:
        _run_mask_subprocess(["docker", "rm", "-f", container], timeout=_SCRATCH_COMMAND_TIMEOUT)


def _await_scratch_readiness(container: str, database: str, *, attempts: int) -> None:
    """Poll `pg_isready` until the scratch database accepts connections."""
    for attempt in range(attempts):
        completed = _run_mask_subprocess(
            ["docker", "exec", container, "pg_isready", "-U", "postgres", "-d", database],
            timeout=_SCRATCH_COMMAND_TIMEOUT,
        )
        if completed.returncode == 0:
            return
        if attempt < attempts - 1:
            time.sleep(_READINESS_INTERVAL_SECONDS)
    raise MaskScratchUnavailableError()


def _quote_identifier(value: str) -> str:
    """Double-quote a rule selector so `-` and reserved words are literal."""
    if _SQL_IDENTIFIER.fullmatch(value) is None:
        raise InvalidMaskSelectorError()
    return f'"{value}"'


def _quote_literal(value: str) -> str:
    """Render `value` as a SQL string literal, doubling embedded single quotes."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _mask_expression(rule: AnonymizationRule, column: str) -> str:
    """Return the SQL expression `column` is replaced with, per `rule`'s strategy."""
    match rule.mask_strategy:
        case MaskStrategy.HASH:
            # md5 over the text rendering: deterministic, so equal inputs stay equal
            # (joins and uniqueness survive masking) while the original is not
            # recoverable from the dump.
            return f"md5({column}::text)"
        case MaskStrategy.NULLIFY:
            return "NULL"
        case MaskStrategy.REDACT:
            return _quote_literal(_REDACTED_MARKER)
        case MaskStrategy.STATIC_REPLACE:
            # `AnonymizationRule` already rejects a static_replace rule without a
            # static_value, so this cannot be None here.
            return _quote_literal(rule.static_value or "")


def _update_statement(rule: AnonymizationRule) -> str:
    table = _quote_identifier(rule.table)
    column = _quote_identifier(rule.column)
    return f"UPDATE {table} SET {column} = {_mask_expression(rule, column)}"


def make_docker_mask_transform(
    *,
    store: StagedArtifactStore,
    runner: DockerMaskRunner = _run_mask_subprocess,
    scratch_factory: ScratchDatabaseFactory = docker_scratch_database,
    timeout: float = _DEFAULT_MASK_TIMEOUT,
) -> Callable[[RestoreSetComponent, tuple[AnonymizationRule, ...]], RestoreSetComponent]:
    """Build the production `MaskTransform` (see the module docstring for the design).

    Structurally satisfies `odoo_forge.anonymization.apply.MaskTransform`.
    """

    def _mask(
        component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
    ) -> RestoreSetComponent:
        if not rules or component.kind is not ArtifactComponentKind.DATABASE:
            # No rules: a round trip would churn the digest for nothing. Filestore:
            # a metadata-only placeholder (D6) with no staged blob to mask.
            return component
        statements = [_update_statement(rule) for rule in rules]
        raw_path = _open_staged_bytes(store, component)
        masked_path: Path | None = None
        try:
            with scratch_factory() as scratch:
                _restore_into_scratch(runner, scratch, raw_path, timeout=timeout)
                _apply_statements(runner, scratch, statements, timeout=timeout)
                masked_path, digest = _redump_from_scratch(runner, scratch, timeout=timeout)
            _stage_masked_bytes(store, digest, masked_path)
        finally:
            if masked_path is not None:
                masked_path.unlink(missing_ok=True)
        return RestoreSetComponent(
            kind=component.kind,
            opaque_component_ref=component.opaque_component_ref,
            format_version=component.format_version,
            digest=digest,
        )

    return _mask


def _open_staged_bytes(store: StagedArtifactStore, component: RestoreSetComponent) -> Path:
    """Resolve the component's staged, digest-verified raw bytes."""
    try:
        return store.open_component(component)
    except Exception as exc:
        raise MaskPersistenceError() from exc


def _restore_into_scratch(
    runner: DockerMaskRunner, scratch: ScratchDatabase, raw_path: Path, *, timeout: float
) -> None:
    argv = [
        "docker",
        "exec",
        "-i",
        scratch.container,
        "pg_restore",
        "-U",
        "postgres",
        "-d",
        scratch.database,
        "--no-owner",
        "--clean",
        "--if-exists",
    ]
    # Opened here rather than inside the runner so a `FileNotFoundError` from the
    # runner can only mean `docker` is missing (same split as `restore_target.py`).
    with raw_path.open("rb") as stream:
        _invoke(runner, argv, stdin=stream, timeout=timeout)


def _apply_statements(
    runner: DockerMaskRunner,
    scratch: ScratchDatabase,
    statements: Sequence[str],
    *,
    timeout: float,
) -> None:
    """Apply every rule's `UPDATE`, aborting on the first one that fails."""
    for statement in statements:
        argv = [
            "docker",
            "exec",
            scratch.container,
            "psql",
            "-U",
            "postgres",
            "-d",
            scratch.database,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            statement,
        ]
        _invoke(runner, argv, timeout=timeout)


def _redump_from_scratch(
    runner: DockerMaskRunner, scratch: ScratchDatabase, *, timeout: float
) -> tuple[Path, ArtifactDigest]:
    """Re-dump the masked database into a staged temp file and hash it back.

    Mirrors `capture.py`'s streamed-dump discipline: written straight to disk,
    hashed in bounded chunks, never held in memory. One `try/except
    BaseException` spans creation, dump, close, and readback, so no failure
    leaks the temp file.
    """
    argv = [
        "docker",
        "exec",
        scratch.container,
        "pg_dump",
        "-U",
        "postgres",
        "--format=custom",
        scratch.database,
    ]
    staged_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=_STAGED_FILE_PREFIX, delete=False) as staged:
            staged_path = Path(staged.name)
            _invoke(runner, argv, stdout=staged, timeout=timeout)
        hasher = hashlib.sha256()
        with staged_path.open("rb") as readback:
            while chunk := readback.read(_CHUNK_SIZE):
                hasher.update(chunk)
    except BaseException:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        raise
    return staged_path, ArtifactDigest(algorithm="sha256", value=hasher.hexdigest())


def _stage_masked_bytes(
    store: StagedArtifactStore, digest: ArtifactDigest, masked_path: Path
) -> None:
    try:
        store.stage(digest, masked_path)
    except Exception as exc:
        raise MaskPersistenceError() from exc


def _invoke(
    runner: DockerMaskRunner,
    argv: Sequence[str],
    *,
    stdin: IO[bytes] | None = None,
    stdout: IO[bytes] | None = None,
    timeout: float,
) -> None:
    """Run one masking command, mapping every subprocess outcome to the taxonomy."""
    try:
        completed = runner(argv, stdin=stdin, stdout=stdout, timeout=timeout)
    except FileNotFoundError as exc:
        raise MaskBinaryUnavailableError() from exc
    except subprocess.TimeoutExpired as exc:
        raise MaskTimeoutError() from exc
    if completed.returncode != 0:
        raise MaskCommandFailedError()


__all__ = [
    "DockerMaskRunner",
    "InvalidMaskSelectorError",
    "MaskBinaryUnavailableError",
    "MaskCommandFailedError",
    "MaskPersistenceError",
    "MaskScratchUnavailableError",
    "MaskTimeoutError",
    "ScratchDatabase",
    "ScratchDatabaseFactory",
    "docker_scratch_database",
    "make_docker_mask_transform",
]
