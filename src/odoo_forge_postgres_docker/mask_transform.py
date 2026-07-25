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
failure path, and runs with `--network none` throughout, because for as long as
it exists it holds the raw PII (see `docker_scratch_database`).

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
# Two DIFFERENT namespaces, deliberately spelled differently. They previously shared a
# literal, so a maintainer changing one and assuming the other followed would have
# renamed the wrong resource: one names a file on the host, the other a Docker container.
_STAGED_FILE_PREFIX = "odoo-forge-mask-dump-"
_SCRATCH_NAME_PREFIX = "odoo-forge-mask-scratch-"

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


class MaskSelectorNotFoundError(DatabaseOperationError):
    """A rule selects a table or column that does not exist in the captured database."""

    public_detail = "anonymization rule targets a table or column that does not exist"


class MaskColumnTypeUnsupportedError(DatabaseOperationError):
    """A rule's strategy cannot produce a value assignable to its column's type."""

    public_detail = "anonymization strategy cannot mask a column of this type"


class MaskUniqueColumnCollisionError(DatabaseOperationError):
    """A rule would collapse a UNIQUE or PRIMARY KEY column to one repeated value."""

    public_detail = "anonymization strategy would violate a unique constraint"


class MaskNotNullColumnError(DatabaseOperationError):
    """A `nullify` rule targets a NOT NULL column."""

    public_detail = "anonymization strategy would violate a not-null constraint"


class MaskScratchNotIsolatedError(DatabaseOperationError):
    """The scratch database is attached to a network and must not receive raw data."""

    public_detail = "scratch masking database is not network-isolated"


class _Deadline:
    """One wall-clock budget shared by every command in a masking round trip.

    `timeout` used to be handed to each command individually, so a round trip with N
    rules could legitimately block for `(2 + N) * timeout` — with the 3600s default and
    twenty rules, ~22 hours before anything fired. The budget is now allocated ONCE and
    drawn down, so `timeout` means what a caller would assume it means.
    """

    def __init__(self, timeout: float) -> None:
        self._expires_at = time.monotonic() + timeout

    def remaining(self) -> float:
        """Return the time left, raising as soon as the budget is spent."""
        left = self._expires_at - time.monotonic()
        if left <= 0:
            raise MaskTimeoutError()
        return left


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
    within the safe identifier shape the sibling adapters validate.

    `--network none` is load-bearing, not hygiene. This container holds the RAW,
    un-anonymized database for the duration of the round trip. Omitting the flag
    attaches it to Docker's default bridge, where every other container on that
    bridge can reach its `5432` directly — no published port required — so the
    raw PII would be readable by any neighbour that can authenticate. With
    `--network none` the container has no interface at all, and `docker exec`
    (which is not network-based) still reaches it over the local socket.

    Because nothing can connect from outside, no password is needed, so
    `POSTGRES_HOST_AUTH_METHOD=trust` replaces a `POSTGRES_PASSWORD` env: a
    password here would be a fixed, hardcoded secret sitting in `docker run`
    argv and readable via `docker inspect`, which is exactly what
    `provider.py`'s credential-injection contract forbids (secrets reach a
    Postgres container only through a bind-mounted `POSTGRES_PASSWORD_FILE`,
    never through env or labels). Trust auth is safe ONLY in combination with
    `--network none`; the two must be changed together or not at all.

    `docker rm -f` runs in a `finally` covering the readiness wait as well as
    the body: a container that never became ready may still have started, and
    while it exists it may hold raw, un-anonymized data.
    """
    container = f"{_SCRATCH_NAME_PREFIX}{uuid.uuid4().hex}"
    # `docker run` is INSIDE the try: a client-side failure (missing binary, timeout
    # while the daemon is still creating the container) can leave a container the
    # daemon finished creating after we gave up, and until it is removed it may hold
    # raw data. The `finally` therefore has to cover the start attempt itself, not
    # just the readiness wait and the body.
    try:
        _invoke(
            _run_mask_subprocess,
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container,
                "--network",
                "none",
                "--env",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "--env",
                f"POSTGRES_DB={database}",
                image,
            ],
            timeout=_SCRATCH_COMMAND_TIMEOUT,
            # A nonzero `docker run` (bad image, daemon out of resources) means no
            # container exists to become ready; say so now instead of burning the whole
            # readiness loop and reporting a misleading "never became ready".
            failure=MaskScratchUnavailableError,
        )
        _await_scratch_readiness(container, database, attempts=readiness_attempts)
        _require_network_isolation(container)
        yield ScratchDatabase(container=container, database=database)
    finally:
        _run_mask_subprocess(["docker", "rm", "-f", container], timeout=_SCRATCH_COMMAND_TIMEOUT)


def _require_network_isolation(container: str) -> None:
    """Refuse to load raw PII into a container that is reachable over the network.

    Defense in depth for the `--network none` + trust-auth pairing. Trust auth is only
    safe BECAUSE nothing can connect from outside; a refactor that dropped the flag
    while keeping trust auth would leave an unauthenticated database full of raw PII
    reachable by every container on the default bridge, and nothing would fail. Asking
    the daemon what actually happened — rather than trusting the argv we just built —
    is what makes the guarantee hold at runtime instead of only in a docstring.
    """
    completed = subprocess.run(  # noqa: S603 - argv-only, shell=False, never a shell string
        [
            "docker",
            "inspect",
            "-f",
            "{{range $network, $_ := .NetworkSettings.Networks}}{{$network}} {{end}}",
            container,
        ],
        capture_output=True,
        check=False,
        shell=False,
        timeout=_SCRATCH_COMMAND_TIMEOUT,
    )
    # `stdout` is None whenever the output was not captured. Treat "cannot tell" as
    # "not proven isolated" rather than assuming the best: this guard exists precisely
    # to stop raw PII entering a reachable container.
    if completed.returncode != 0 or completed.stdout is None:
        raise MaskScratchNotIsolatedError()
    attached = completed.stdout.decode(errors="replace").split()
    if attached not in ([], ["none"]):
        raise MaskScratchNotIsolatedError()


def _await_scratch_readiness(container: str, database: str, *, attempts: int) -> None:
    """Poll until `database` itself answers a query.

    Deliberately a real `psql` query and NOT `pg_isready`: the postgres image's
    entrypoint runs a TEMPORARY bootstrap server during initdb, and `pg_isready`
    reports success against that bootstrap server — before `POSTGRES_DB` has been
    created. It also ignores its own `-d` argument for existence purposes. Probing
    with `pg_isready` therefore returns "ready" too early, and the `pg_restore` that
    follows fails against a database that does not exist yet. Only a query executed
    against the target database proves the database is really there.
    """
    for attempt in range(attempts):
        completed = _run_mask_subprocess(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-tAc",
                "SELECT 1",
            ],
            timeout=_SCRATCH_COMMAND_TIMEOUT,
        )
        if completed.returncode == 0:
            return
        if attempt < attempts - 1:
            time.sleep(_READINESS_INTERVAL_SECONDS)
    raise MaskScratchUnavailableError()


@dataclass(frozen=True)
class _ColumnFacts:
    """What the scratch database knows about one rule's target column."""

    data_type: str
    is_unique: bool
    is_nullable: bool


# Types `md5(...)` and a quoted literal can be assigned back into directly. Anything
# else (integer, uuid, timestamp, jsonb, ...) has no implicit assignment cast from
# text, so Postgres rejects the UPDATE outright.
_TEXT_ASSIGNABLE_TYPES = frozenset({"text", "character varying", "character"})

_INTROSPECTION_SQL = """
SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
  EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.table_name = c.table_name
      AND kcu.column_name = c.column_name
      AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
  ) AS is_unique
FROM information_schema.columns c
WHERE (c.table_name, c.column_name) IN (%s)
"""


def _introspect_columns(
    runner: DockerMaskRunner,
    scratch: ScratchDatabase,
    rules: Sequence[AnonymizationRule],
    *,
    deadline: _Deadline,
) -> dict[tuple[str, str], _ColumnFacts]:
    """Read the real type and constraints of every rule's target column.

    One round trip for all rules. Without this, an unmaskable rule surfaced as a
    generic `MaskCommandFailedError` with the reason discarded to `DEVNULL` — an
    operator saw "masking command failed" and had nothing to act on. Knowing the
    schema up front lets each incompatibility raise its own named error BEFORE any
    row is touched.
    """
    pairs = ", ".join(
        f"({_quote_literal(rule.table)}, {_quote_literal(rule.column)})" for rule in rules
    )
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
        "-tAc",
        _INTROSPECTION_SQL % pairs,
    ]
    with tempfile.NamedTemporaryFile(prefix=_STAGED_FILE_PREFIX, delete=True) as sink:
        _invoke(runner, argv, stdout=sink, timeout=deadline.remaining())
        sink.flush()
        rows = Path(sink.name).read_text(encoding="utf-8")
    facts: dict[tuple[str, str], _ColumnFacts] = {}
    for line in rows.splitlines():
        if not line.strip():
            continue
        table, column, data_type, is_nullable, is_unique = line.split("|")
        facts[(table, column)] = _ColumnFacts(
            data_type=data_type,
            is_unique=is_unique == "t",
            is_nullable=is_nullable == "YES",
        )
    return facts


def _require_maskable(
    rules: Sequence[AnonymizationRule], facts: dict[tuple[str, str], _ColumnFacts]
) -> None:
    """Fail closed, with a NAMED reason, before any row is modified.

    Every check here corresponds to an `UPDATE` Postgres would reject anyway; the
    point is that the caller learns WHICH rule is wrong and WHY, instead of a
    generic command failure, and that the scratch database is never left
    half-masked by a batch that dies partway through.
    """
    for rule in rules:
        column = facts.get((rule.table, rule.column))
        if column is None:
            raise MaskSelectorNotFoundError()
        writes_text = rule.mask_strategy in (
            MaskStrategy.HASH,
            MaskStrategy.REDACT,
            MaskStrategy.STATIC_REPLACE,
        )
        if writes_text and column.data_type not in _TEXT_ASSIGNABLE_TYPES:
            raise MaskColumnTypeUnsupportedError()
        collapses_to_one_value = rule.mask_strategy in (
            MaskStrategy.REDACT,
            MaskStrategy.STATIC_REPLACE,
        )
        if collapses_to_one_value and column.is_unique:
            raise MaskUniqueColumnCollisionError()
        if rule.mask_strategy is MaskStrategy.NULLIFY and not column.is_nullable:
            raise MaskNotNullColumnError()


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
        # ONE budget for the whole round trip, drawn down per command — not `timeout`
        # handed afresh to each of the (2 + N) commands.
        deadline = _Deadline(timeout)
        masked_path: Path | None = None
        try:
            with scratch_factory() as scratch:
                _restore_into_scratch(runner, scratch, raw_path, deadline=deadline)
                # Validate every rule against the REAL schema before touching a row, so
                # an unmaskable rule names itself instead of dying mid-batch as a
                # generic command failure.
                _require_maskable(
                    rules, _introspect_columns(runner, scratch, rules, deadline=deadline)
                )
                _apply_statements(runner, scratch, statements, deadline=deadline)
                masked_path, digest = _redump_from_scratch(runner, scratch, deadline=deadline)
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
    runner: DockerMaskRunner, scratch: ScratchDatabase, raw_path: Path, *, deadline: _Deadline
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
        _invoke(runner, argv, stdin=stream, timeout=deadline.remaining())


def _apply_statements(
    runner: DockerMaskRunner,
    scratch: ScratchDatabase,
    statements: Sequence[str],
    *,
    deadline: _Deadline,
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
        _invoke(runner, argv, timeout=deadline.remaining())


def _redump_from_scratch(
    runner: DockerMaskRunner, scratch: ScratchDatabase, *, deadline: _Deadline
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
            _invoke(runner, argv, stdout=staged, timeout=deadline.remaining())
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
    failure: type[DatabaseOperationError] = MaskCommandFailedError,
) -> None:
    """Run one masking command, mapping every subprocess outcome to the taxonomy.

    `failure` lets a caller name what a nonzero exit means in ITS context (a failed
    `docker run` is an unavailable scratch database, not a failed masking command)
    without duplicating the binary/timeout mapping.
    """
    try:
        completed = runner(argv, stdin=stdin, stdout=stdout, timeout=timeout)
    except FileNotFoundError as exc:
        raise MaskBinaryUnavailableError() from exc
    except subprocess.TimeoutExpired as exc:
        raise MaskTimeoutError() from exc
    if completed.returncode != 0:
        raise failure()


__all__ = [
    "DockerMaskRunner",
    "InvalidMaskSelectorError",
    "MaskBinaryUnavailableError",
    "MaskCommandFailedError",
    "MaskPersistenceError",
    "MaskColumnTypeUnsupportedError",
    "MaskNotNullColumnError",
    "MaskScratchNotIsolatedError",
    "MaskScratchUnavailableError",
    "MaskSelectorNotFoundError",
    "MaskUniqueColumnCollisionError",
    "MaskTimeoutError",
    "ScratchDatabase",
    "ScratchDatabaseFactory",
    "docker_scratch_database",
    "make_docker_mask_transform",
]
