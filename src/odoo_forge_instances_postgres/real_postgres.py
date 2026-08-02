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


def _run(argv: Sequence[str], *, env: Mapping[str, str], timeout: float) -> CompletedProcess[str]:
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
    try:
        result = runner(argv, env=env, timeout=timeout)
    except PostgresHarnessError:
        raise
    except Exception:
        raise PostgresHarnessError("docker command execution failed") from None
    if result.returncode != 0:
        raise PostgresHarnessError(f"docker command failed with exit code {result.returncode}")
    return result


def _probe(runner: Runner, argv: Sequence[str], *, timeout: float) -> CompletedProcess[str]:
    try:
        return runner(argv, env={}, timeout=timeout)
    except PostgresHarnessError:
        raise
    except Exception:
        raise PostgresHarnessError("docker command execution failed") from None


def _names(token: str) -> dict[str, str]:
    return {
        "network": f"odoo-forge-pg-network-{token}",
        "volume": f"odoo-forge-pg-volume-{token}",
        "container": f"odoo-forge-pg-container-{token}",
        "database": f"odoo_{token}",
        "user": f"odoo_{token}",
    }


def _ownership(runner: Runner, kind: str, name: str, token: str, *, timeout: float) -> str:
    label_path = ".Config.Labels" if kind == "container" else ".Labels"
    result = _probe(
        runner,
        [
            "docker",
            "inspect",
            f'--format={{{{index {label_path} "odoo-forge-harness-token"}}}}',
            name,
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        return "missing" if "no such" in (result.stderr or "").lower() else "inspect-failed"
    return "owned" if (result.stdout or "").strip() == token else "foreign"


def _cleanup_resource(
    runner: Runner,
    kind: str,
    name: str,
    token: str,
    argv: Sequence[str],
    residuals: list[str],
    *,
    timeout: float,
) -> bool:
    try:
        state = _ownership(runner, kind, name, token, timeout=timeout)
    except Exception:
        state = "inspect-failed"
    if state == "missing":
        return False
    if state == "foreign":
        residuals.append(f"{kind}:ownership-mismatch")
        return False
    if state == "inspect-failed":
        residuals.append(f"{kind}:inspect-failed")
        return False
    try:
        result = _probe(runner, argv, timeout=timeout)
    except PostgresHarnessError:
        residuals.append(f"{kind}:remove-failed")
        return False
    if result.returncode != 0:
        residuals.append(f"{kind}:remove-failed:{result.returncode}")
        return False
    return True


@contextmanager
def postgres_harness(
    *,
    host: str = "127.0.0.1",
    port: int = 5432,
    image: str = "postgres:16",
    startup_timeout: float = 30.0,
    poll_interval: float = 0.1,
    remove_persisted_state: bool = False,
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
    created: set[str] = set()
    body_error: BaseException | None = None
    try:
        _checked(
            runner,
            [
                "docker",
                "network",
                "create",
                "--label",
                f"odoo-forge-harness-token={token}",
                names["network"],
            ],
            env={},
            timeout=timeout,
        )
        created.add("network")
        _checked(
            runner,
            [
                "docker",
                "volume",
                "create",
                "--label",
                f"odoo-forge-harness-token={token}",
                names["volume"],
            ],
            env={},
            timeout=timeout,
        )
        created.add("volume")
        _checked(
            runner,
            [
                "docker",
                "run",
                "--detach",
                "--name",
                names["container"],
                "--label",
                f"odoo-forge-harness-token={token}",
                "--network",
                names["network"],
                "--publish",
                f"{port}:5432",
                "--env",
                "POSTGRES_DB",
                "--env",
                "POSTGRES_USER",
                "--env",
                "POSTGRES_PASSWORD",
                "--mount",
                f"source={names['volume']},destination=/var/lib/postgresql/data",
                image,
            ],
            env={"POSTGRES_DB": names["database"], "POSTGRES_USER": names["user"], **env},
            timeout=timeout,
        )
        created.add("container")

        deadline = clock() + startup_timeout
        readiness = [
            "docker",
            "exec",
            "--",
            names["container"],
            "pg_isready",
            "--username",
            names["user"],
            "--dbname",
            names["database"],
        ]
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                raise PostgresHarnessError(
                    f"postgres readiness timed out after {startup_timeout:g}s"
                )
            if _probe(runner, readiness, timeout=min(timeout, remaining)).returncode == 0:
                break
            state = _probe(
                runner,
                ["docker", "inspect", "--format={{.State.Status}}", names["container"]],
                timeout=min(timeout, remaining),
            )
            if state.returncode == 0 and (state.stdout or "").strip() in {"exited", "dead"}:
                raise PostgresHarnessError("postgres process exited before readiness")
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
        cleanup = (
            ("container", ["docker", "rm", "--force", names["container"]]),
            ("network", ["docker", "network", "rm", names["network"]]),
        )
        for kind, argv in cleanup:
            if kind in created:
                _cleanup_resource(
                    runner, kind, names[kind], token, argv, residuals, timeout=timeout
                )
        retained: list[str] = []
        if "volume" in created:
            volume_name = names["volume"]
            if remove_persisted_state:
                _cleanup_resource(
                    runner,
                    "volume",
                    volume_name,
                    token,
                    ["docker", "volume", "rm", volume_name],
                    residuals,
                    timeout=timeout,
                )
            else:
                try:
                    volume_state = _ownership(runner, "volume", volume_name, token, timeout=timeout)
                except Exception:
                    volume_state = "inspect-failed"
                if volume_state == "owned":
                    retained.append(f"volume:{volume_name}")
                elif volume_state == "missing":
                    pass
                else:
                    residuals.append(f"volume:{volume_state}")
        session.cleanup_report = CleanupReport(tuple(residuals), tuple(retained))
        if residuals and body_error is None:
            raise PostgresHarnessError(f"cleanup incomplete: {', '.join(residuals)}")
        if residuals and body_error is not None:
            body_error.add_note(f"postgres harness cleanup residuals: {', '.join(residuals)}")
