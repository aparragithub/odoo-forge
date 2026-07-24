"""Docker-backed capture adapter producing a raw restore set manifest from a live source.

Runs `pg_dump` argv-only (`shell=False`), never through a shell, and rejects
any source identifier that does not match the safe container/database
identifier shape (`_IDENTIFIER`). The `ArtifactDigest` is computed from the
captured bytes BEFORE `capture()` returns (never deferred to delivery time,
per spec) — but, unlike a naive `subprocess.run(capture_output=True)`, the
dump is streamed to a staged temporary file and hashed back in bounded chunks
(`_CHUNK_SIZE`) so a multi-GB dump is never held fully in memory. The
temporary file is always removed once hashing completes (or on failure).

The filestore component is a pass-through seam (`FilestoreCaptureSeam`) that
emits a deterministic, zero-content component with `format_version="empty-v1"`
until a real filestore capture adapter exists; the manifest shape and validator
(exactly one database + one filestore component) require no change when that
adapter is composed in later (D6).

Anonymization decisions are explicitly OUT of scope here (D4): this adapter
always returns the RAW, un-anonymized manifest.

Error taxonomy: four distinct `DatabaseOperationError` subclasses so callers
can tell apart four failure modes — a missing `docker` binary
(`CaptureBinaryUnavailableError`), a bounded timeout enforced by
`subprocess.run(..., timeout=)` (`CaptureTimeoutError`), a nonzero exit
(`CaptureCommandFailedError`), and a rejected (unsafe) source identifier
(`InvalidCaptureIdentifierError`). This is a genuine 3-way subprocess-outcome
split plus identifier validation for THIS adapter's own needs; it is not a
claim of exact parity with `provider.py`'s narrower two-error split. Every
error carries only a fixed, redacted-safe `public_detail` — never raw stderr,
argv, or connection material — matching `DatabaseOperationError`'s existing
redaction contract.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
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


@dataclass(frozen=True)
class CaptureRunResult:
    """The outcome of one streamed capture subprocess invocation.

    `digest_hex` is always computed incrementally, in bounded chunks, over the
    captured stdout stream — never from a fully materialized in-memory buffer.
    """

    returncode: int
    digest_hex: str


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
    reading that file back in bounded `_CHUNK_SIZE` chunks; the temp file is
    always removed afterward.
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
            hasher = hashlib.sha256()
            with staged_path.open("rb") as readback:
                while chunk := readback.read(_CHUNK_SIZE):
                    hasher.update(chunk)
            return CaptureRunResult(returncode=completed.returncode, digest_hex=hasher.hexdigest())
        finally:
            staged_path.unlink(missing_ok=True)


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
        runner: DockerCaptureRunner = _run_subprocess,
        timeout: float = _DEFAULT_CAPTURE_TIMEOUT,
        filestore_seam: FilestoreCaptureSeam = emit_empty_filestore_component,
    ) -> None:
        self._runner = runner
        self._timeout = timeout
        self._filestore_seam = filestore_seam

    def capture(self, source: CaptureSource) -> RestoreSetManifest:
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
        result = self._run(argv)
        digest = ArtifactDigest(algorithm="sha256", value=result.digest_hex)
        database_component = RestoreSetComponent(
            kind=ArtifactComponentKind.DATABASE,
            opaque_component_ref=f"database-{container}",
            format_version="pg_dump-custom-v1",
            digest=digest,
        )
        return RestoreSetManifest(
            restore_set_id=f"restore-set-{container}",
            lineage_id=f"lineage-{container}",
            components=(database_component, self._filestore_seam()),
        )

    def _run(self, argv: Sequence[str]) -> CaptureRunResult:
        try:
            result = self._runner(argv, timeout=self._timeout)
        except FileNotFoundError as exc:
            raise CaptureBinaryUnavailableError() from exc
        except subprocess.TimeoutExpired as exc:
            # `subprocess.run(..., timeout=)` already killed the child process
            # (including a stalled producer that never wrote any output), so
            # there is no orphan to clean up here.
            raise CaptureTimeoutError() from exc
        if result.returncode != 0:
            raise CaptureCommandFailedError()
        return result

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if _IDENTIFIER.fullmatch(value) is None:
            raise InvalidCaptureIdentifierError()


__all__ = [
    "CaptureBinaryUnavailableError",
    "CaptureCommandFailedError",
    "CaptureRunResult",
    "CaptureTimeoutError",
    "DockerCaptureRunner",
    "DockerPostgresqlCaptureAdapter",
    "FilestoreCaptureSeam",
    "InvalidCaptureIdentifierError",
    "emit_empty_filestore_component",
]
