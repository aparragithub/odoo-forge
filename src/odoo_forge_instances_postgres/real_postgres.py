"""Synchronous, driver-neutral PostgreSQL Docker harness boundary."""

from __future__ import annotations

import os
import secrets
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from subprocess import CompletedProcess
from typing import Protocol

__all__ = [
    "CleanupReport",
    "PostgresConnectionInfo",
    "PostgresHarnessError",
    "PostgresSession",
    "postgres_harness",
]


class Runner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> CompletedProcess[str]: ...


class PostgresHarnessError(RuntimeError):
    """Raised when bounded harness startup or cleanup cannot complete."""


@dataclass(frozen=True)
class PostgresConnectionInfo:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class CleanupReport:
    residuals: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()


@dataclass
class PostgresSession:
    connection: PostgresConnectionInfo
    cleanup_report: CleanupReport | None = None


def _run(
    argv: Sequence[str], *, env: Mapping[str, str], timeout: float
) -> CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            capture_output=True,
            check=False,
            env={**os.environ, **env},
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        raise PostgresHarnessError("docker command execution failed") from None


def _checked(
    runner: Runner, argv: Sequence[str], *, env: Mapping[str, str], timeout: float
) -> CompletedProcess[str]:
    result = runner(argv, env=env, timeout=timeout)
    if result.returncode != 0:
        raise PostgresHarnessError(f"docker command failed with exit code {result.returncode}")
    return result


def _names(token: str) -> dict[str, str]:
    return {
        "network": f"odoo-forge-pg-network-{token}",
        "volume": f"odoo-forge-pg-volume-{token}",
        "container": f"odoo-forge-pg-container-{token}",
        "database": f"odoo_{token}",
        "user": f"odoo_{token}",
    }


@contextmanager
def postgres_harness(
    *,
    host: str = "127.0.0.1",
    port: int = 5432,
    image: str = "postgres:16",
    startup_timeout: float = 30.0,
    poll_interval: float = 0.1,
    runner: Runner = _run,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    token_factory: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
) -> Iterator[PostgresSession]:
    """Own one tokenized PostgreSQL process and yield external connection fields."""
    if startup_timeout <= 0 or poll_interval <= 0:
        raise ValueError("startup_timeout and poll_interval must be positive")

    token = token_factory()
    names = _names(token)
    password = secrets.token_urlsafe(24)
    env = {"POSTGRES_PASSWORD": password}
    session = PostgresSession(
        PostgresConnectionInfo(host, port, names["database"], names["user"], password)
    )
    timeout = startup_timeout
    body_error: BaseException | None = None
    try:
        _checked(
            runner,
            [
                "docker", "network", "create", "--label",
                f"odoo-forge-harness-token={token}", names["network"],
            ],
            env={},
            timeout=timeout,
        )
        _checked(
            runner,
            [
                "docker", "volume", "create", "--label",
                f"odoo-forge-harness-token={token}", names["volume"],
            ],
            env={},
            timeout=timeout,
        )
        _checked(
            runner,
            [
                "docker", "run", "--detach", "--name", names["container"],
                "--network", names["network"], "--publish", f"{port}:5432",
                "--env", "POSTGRES_DB", "--env", "POSTGRES_USER",
                "--env", "POSTGRES_PASSWORD", "--mount",
                f"source={names['volume']},destination=/var/lib/postgresql/data", image,
            ],
            env={"POSTGRES_DB": names["database"], "POSTGRES_USER": names["user"], **env},
            timeout=timeout,
        )

        deadline = clock() + startup_timeout
        readiness = [
            "docker", "exec", "--", names["container"], "pg_isready",
            "--username", names["user"], "--dbname", names["database"],
        ]
        while True:
            if runner(readiness, env={}, timeout=timeout).returncode == 0:
                break
            remaining = deadline - clock()
            if remaining <= 0:
                raise PostgresHarnessError(
                    f"postgres readiness timed out after {startup_timeout:g}s"
                )
            sleep(min(poll_interval, remaining))

        yield session
    except BaseException as error:
        body_error = error
        raise
    finally:
        residuals: list[str] = []
        cleanup = [
            ("container", ["docker", "rm", "--force", names["container"]]),
            ("network", ["docker", "network", "rm", names["network"]]),
        ]
        for label, argv in cleanup:
            try:
                _checked(runner, argv, env={}, timeout=timeout)
            except PostgresHarnessError:
                residuals.append(label)
        session.cleanup_report = CleanupReport(
            tuple(residuals), (f"volume:{names['volume']}",)
        )
        if residuals and body_error is None:
            raise PostgresHarnessError(f"cleanup incomplete: {', '.join(residuals)}")
