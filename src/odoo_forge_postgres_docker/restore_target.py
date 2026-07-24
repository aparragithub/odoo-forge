"""Real production `RestoreTarget` wiring (design D1).

Streams a `database` `RestoreSetComponent`'s staged bytes into a provisioned
container via `docker exec ... pg_restore` (argv-only, no shell, bounded
timeout). A `filestore` component is accepted as a no-op success — the v1
pass-through seam (design D6) never needs a real byte transfer.

Byte resolution (mapping an opaque `RestoreSetComponent` to a local staged
file) is an injected `RestoreByteSource` seam, symmetric to
`CredentialTarget`/`restore_injector` elsewhere in this adapter package: the
default raises rather than silently fabricating a location, so callers must
explicitly wire a real byte source to get a working restore path.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from odoo_forge.data_artifacts.contracts import ArtifactComponentKind, RestoreSetComponent
from odoo_forge.database.errors import DatabaseOperationError

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DEFAULT_RESTORE_TIMEOUT = 3600.0


class RestoreInjectionBinaryUnavailableError(DatabaseOperationError):
    """The `docker` binary required to run the restore command is unavailable."""

    public_detail = "restore command binary is unavailable"


class RestoreInjectionTimeoutError(DatabaseOperationError):
    """A restore subprocess invocation did not complete within its bounded timeout."""

    public_detail = "restore operation timed out"


class RestoreInjectionFailedError(DatabaseOperationError):
    """A restore subprocess invocation returned a nonzero exit status."""

    public_detail = "restore command failed"


class InvalidRestoreIdentifierError(DatabaseOperationError):
    """A restore target identifier does not match the safe container/database shape."""

    public_detail = "restore target identifier is invalid"


class RestoreByteSourceUnavailableError(DatabaseOperationError):
    """The default byte source: no staged bytes are reachable for this component."""

    public_detail = "restore artifact bytes are not accessible from this byte source"


RestoreByteSource = Callable[[RestoreSetComponent], Path]
RestoreTarget = Callable[[RestoreSetComponent, str], bool]


def _unavailable_byte_source(_component: RestoreSetComponent) -> Path:
    raise RestoreByteSourceUnavailableError()


class DockerRestoreRunner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, stdin_path: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]: ...


def _run_restore_subprocess(
    argv: Sequence[str], *, stdin_path: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Stream the staged dump file straight into the subprocess's stdin.

    The file is opened and handed to `subprocess.run` as `stdin=`, so the
    (potentially large) dump is streamed from disk rather than buffered
    fully in memory. `timeout` is delegated entirely to `subprocess.run`,
    which kills a stalled child itself.
    """
    with stdin_path.open("rb") as stream:
        return subprocess.run(  # noqa: S603 - argv-only, shell=False, never a shell string
            list(argv),
            stdin=stream,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=timeout,
        )


def make_docker_restore_target(
    *,
    byte_source: RestoreByteSource = _unavailable_byte_source,
    runner: DockerRestoreRunner = _run_restore_subprocess,
    timeout: float = _DEFAULT_RESTORE_TIMEOUT,
) -> RestoreTarget:
    """Build a production `RestoreTarget` that streams DB bytes via `pg_restore`.

    A `filestore` component is always accepted as a no-op success (D6); only
    a `database` component identifier is validated and streamed into the
    provisioned container.
    """

    def _restore_target(component: RestoreSetComponent, target: str) -> bool:
        if component.kind is ArtifactComponentKind.FILESTORE:
            return True
        _validate_restore_identifier(target)
        staged_path = byte_source(component)
        argv = [
            "docker",
            "exec",
            "-i",
            target,
            "pg_restore",
            "-U",
            "postgres",
            "-d",
            target,
            "--no-owner",
            "--clean",
            "--if-exists",
        ]
        try:
            completed = runner(argv, stdin_path=staged_path, timeout=timeout)
        except FileNotFoundError as exc:
            raise RestoreInjectionBinaryUnavailableError() from exc
        except subprocess.TimeoutExpired as exc:
            raise RestoreInjectionTimeoutError() from exc
        if completed.returncode != 0:
            raise RestoreInjectionFailedError()
        return True

    return _restore_target


def _validate_restore_identifier(value: str) -> None:
    if _IDENTIFIER.fullmatch(value) is None:
        raise InvalidRestoreIdentifierError()


__all__ = [
    "DockerRestoreRunner",
    "InvalidRestoreIdentifierError",
    "RestoreByteSource",
    "RestoreByteSourceUnavailableError",
    "RestoreInjectionBinaryUnavailableError",
    "RestoreInjectionFailedError",
    "RestoreInjectionTimeoutError",
    "RestoreTarget",
    "make_docker_restore_target",
]
