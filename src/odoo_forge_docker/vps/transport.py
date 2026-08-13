"""Fail-closed system OpenSSH/scp transport for one pinned VPS target."""

from __future__ import annotations

import math
import os
import re
import shlex
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/@:+%=\-^$,]+$")
_PRE_MUTATION_MARKERS = (
    "host key verification failed",
    "remote host identification has changed",
    "permission denied",
    "could not resolve hostname",
    "connection timed out",
    "connection refused",
    "no route to host",
    "batchmode",
)


class MutationState(Enum):
    PRE_MUTATION = "pre_mutation"
    UNKNOWN_POST_MUTATION = "unknown_post_mutation"


class InvalidRemoteInputError(ValueError):
    """A remote token is not safe to place in a fixed command argv."""


class TransportFailure(RuntimeError):
    """A redacted transport failure with an explicit mutation boundary."""

    def __init__(self, state: MutationState) -> None:
        self.state = state
        detail = (
            "secure OpenSSH transport failed before mutation"
            if state is MutationState.PRE_MUTATION
            else "secure OpenSSH transport failed; reconciliation required"
        )
        super().__init__(detail)


class UnknownMutationOutcomeError(TransportFailure):
    """The remote side may have changed state before transport failed."""

    def __init__(self) -> None:
        super().__init__(MutationState.UNKNOWN_POST_MUTATION)


@dataclass(frozen=True)
class OpenSshTarget:
    """Pinned connection material; the private key never enters process argv."""

    host: str
    user: str
    port: int
    host_key: str
    private_key: str

    def __post_init__(self) -> None:
        if not _HOST_RE.fullmatch(self.host) or not _HOST_RE.fullmatch(self.user):
            raise InvalidRemoteInputError("invalid SSH target")
        if not 1 <= self.port <= 65535 or "\n" in self.host_key or not self.host_key.strip():
            raise InvalidRemoteInputError("invalid SSH target")
        if not self.private_key.strip():
            raise InvalidRemoteInputError("missing SSH identity")


@dataclass(frozen=True)
class CommandResult:
    """Safe command evidence; stdout and stderr are redacted before return."""

    returncode: int
    stdout: str
    stderr: str


class OpenSshTransport:
    """Execute validated remote commands and secure secret transfers."""

    def __init__(
        self,
        target: OpenSshTarget,
        *,
        timeout: float = 30.0,
        staging_root: Path | None = None,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if staging_root is not None and not staging_root.is_dir():
            raise ValueError("staging root must be an existing directory")
        self._target = target
        self._timeout = timeout
        self._staging_root = staging_root

    @property
    def _connect_timeout(self) -> int:
        """Return OpenSSH's integer timeout without exceeding subprocess bounds."""
        return max(1, math.ceil(self._timeout) - 1)

    def run(self, command: Sequence[str], *, mutating: bool = False) -> CommandResult:
        """Run one validated remote command through `ssh`, never a local shell."""
        tokens = _validated_tokens(command)
        with self._materialized_files() as (identity, known_hosts):
            argv = self._ssh_argv(identity, known_hosts)
            argv.append(shlex.join(tokens))
            return self._invoke(argv, mutating=mutating)

    def upload_secret(
        self, secret: str, remote_path: str, *, mutating: bool = True
    ) -> CommandResult:
        """Stage one secret as 0600, transfer it with scp, and always remove it."""
        _validated_tokens((remote_path,))
        with (
            self._materialized_files() as (identity, known_hosts),
            tempfile.TemporaryDirectory(
                prefix="odoo-forge-vps-",
                dir=str(self._staging_root) if self._staging_root else None,
            ) as directory,
        ):
            source = Path(directory) / "secret"
            _write_private(source, secret)
            destination = f"{self._target.user}@{self._target.host}:{remote_path}"
            argv = self._scp_argv(identity, known_hosts)
            argv.extend([str(source), destination])
            return self._invoke(argv, mutating=mutating, secrets=(secret,))

    def _ssh_argv(self, identity: Path, known_hosts: Path) -> list[str]:
        return [
            "ssh",
            "-p",
            str(self._target.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-F",
            "/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            f"ConnectTimeout={self._connect_timeout}",
            "-i",
            str(identity),
            f"{self._target.user}@{self._target.host}",
        ]

    def _scp_argv(self, identity: Path, known_hosts: Path) -> list[str]:
        return [
            "scp",
            "-P",
            str(self._target.port),
            "-p",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-F",
            "/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            f"ConnectTimeout={self._connect_timeout}",
            "-i",
            str(identity),
        ]

    def _invoke(
        self, argv: list[str], *, mutating: bool, secrets: Sequence[str] = ()
    ) -> CommandResult:
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            if mutating:
                raise UnknownMutationOutcomeError() from exc
            raise TransportFailure(MutationState.PRE_MUTATION) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise TransportFailure(MutationState.PRE_MUTATION) from exc
        stdout = _redact(result.stdout or "", (*secrets, self._target.private_key))
        stderr = _redact(result.stderr or "", (*secrets, self._target.private_key))
        if result.returncode == 0:
            return CommandResult(result.returncode, stdout, stderr)
        if result.returncode != 255:
            return CommandResult(result.returncode, stdout, stderr)
        if not mutating or _is_pre_mutation(stderr):
            raise TransportFailure(MutationState.PRE_MUTATION)
        raise UnknownMutationOutcomeError()

    @contextmanager
    def _materialized_files(self) -> Iterator[tuple[Path, Path]]:
        with tempfile.TemporaryDirectory(
            prefix="odoo-forge-vps-", dir=str(self._staging_root) if self._staging_root else None
        ) as directory:
            root = Path(directory)
            identity = root / "identity"
            known_hosts = root / "known_hosts"
            _write_private(identity, self._target.private_key)
            _write_private(known_hosts, self._target.host_key + "\n")
            yield identity, known_hosts


def _validated_tokens(tokens: Sequence[str]) -> tuple[str, ...]:
    values = tuple(tokens)
    if not values or any(
        not isinstance(token, str) or not _TOKEN_RE.fullmatch(token) for token in values
    ):
        raise InvalidRemoteInputError("unsafe remote command token")
    return values


def _write_private(path: Path, value: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        stream = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        stream.write(value)
    os.chmod(path, 0o600)


def _redact(value: str, secrets: Sequence[str]) -> str:
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    return value


def _is_pre_mutation(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _PRE_MUTATION_MARKERS)


__all__ = [
    "CommandResult",
    "InvalidRemoteInputError",
    "MutationState",
    "OpenSshTarget",
    "OpenSshTransport",
    "TransportFailure",
    "UnknownMutationOutcomeError",
]
