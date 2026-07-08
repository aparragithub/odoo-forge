"""Concrete `BackendProvider` adapter backed by the `docker` CLI.

Structurally satisfies `odoo_forge.ports.backend_provider.BackendProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `docker` (mirrors
`odoo_forge_git.git_provider`).

This module implements the full `run()` orchestration (PR-2a-ii): pure argv
builders, the subprocess boundary, error classification, existence checks
(PR-2a-i), plus readiness gates and created-only rollback (PR-2a-ii).
"""

import json
import os
import subprocess
import time
from typing import Callable

from odoo_forge.backend.errors import (
    ContainerRunError,
    DockerUnavailableError,
    ImageNotFoundError,
    InstanceExistsError,
    PostgresReadinessError,
)
from odoo_forge.backend.plan import BackendPlan, ContainerRole, ContainerSpec, NetworkSpec, VolumeSpec
from odoo_forge.backend.status import InstanceRef, instance_ref

DEFAULT_DOCKER_TIMEOUT_SECONDS = 30.0
DEFAULT_PG_READINESS_TIMEOUT_SECONDS = 30.0
DEFAULT_PG_POLL_INTERVAL_SECONDS = 1.0
# Design floor: HEALTHCHECK start-period=60s + interval=30s + cold-boot margin
# (`Dockerfile:100`). A shorter default would spuriously time out a container
# that is in fact healthy — see design "Odoo readiness gate (step 6)".
DEFAULT_HEALTH_WAIT_TIMEOUT_SECONDS = 180.0
DEFAULT_HEALTH_POLL_INTERVAL_SECONDS = 5.0

_DAEMON_DOWN_MARKER = "Cannot connect to the Docker daemon"
_IMAGE_NOT_FOUND_MARKER = "Unable to find image"

_ROLE_VOLUME_TARGET: dict[ContainerRole, str] = {
    "postgres": "/var/lib/postgresql/data",
    "odoo": "/var/lib/odoo",
}

# ("network", name) | ("volume", name) | ("container", name)
_CreatedResource = tuple[str, str]


def _docker_env() -> dict[str, str]:
    """Subprocess env pinned to `LANG=C`/`LC_ALL=C` for stable stderr markers.

    Mirrors `odoo_forge_git.git_provider._non_interactive_env`.
    """
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


def _network_create_argv(spec: NetworkSpec) -> list[str]:
    argv = ["docker", "network", "create"]
    for key, value in spec.labels.items():
        argv += ["--label", f"{key}={value}"]
    argv.append(spec.name)
    return argv


def _volume_create_argv(spec: VolumeSpec) -> list[str]:
    argv = ["docker", "volume", "create"]
    for key, value in spec.labels.items():
        argv += ["--label", f"{key}={value}"]
    argv.append(spec.name)
    return argv


def _run_container_argv(spec: ContainerSpec) -> list[str]:
    argv = ["docker", "run", "-d", "--name", spec.name, "--network", spec.network]
    for key, value in spec.labels.items():
        argv += ["--label", f"{key}={value}"]
    for key, value in spec.env.items():
        argv += ["-e", f"{key}={value}"]
    target = _ROLE_VOLUME_TARGET[spec.role]
    for volume in spec.volumes:
        argv += ["-v", f"{volume.name}:{target}"]
    for mount in spec.mounts:
        suffix = ":ro" if mount.read_only else ""
        argv += ["-v", f"{mount.host_path}:{mount.container_path}{suffix}"]
    for container_port, host_port in spec.ports.items():
        host = "0" if host_port is None else str(host_port)
        argv += ["-p", f"{host}:{container_port}"]
    argv.append(spec.image)
    return argv


def _health_status(inspect_stdout: str) -> str | None:
    try:
        data = json.loads(inspect_stdout)
    except (ValueError, TypeError):
        return None
    containers = data if isinstance(data, list) else [data]
    if not containers:
        return None
    state = containers[0].get("State") or {}
    health = state.get("Health") or {}
    return health.get("Status")


class DockerBackendProvider:
    """Adapter that maps `BackendPlan` specs to `docker` CLI invocations."""

    def __init__(
        self,
        *,
        docker_timeout: float = DEFAULT_DOCKER_TIMEOUT_SECONDS,
        pg_readiness_timeout: float = DEFAULT_PG_READINESS_TIMEOUT_SECONDS,
        pg_poll_interval: float = DEFAULT_PG_POLL_INTERVAL_SECONDS,
        health_wait_timeout: float = DEFAULT_HEALTH_WAIT_TIMEOUT_SECONDS,
        health_poll_interval: float = DEFAULT_HEALTH_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._docker_timeout = docker_timeout
        self._pg_readiness_timeout = pg_readiness_timeout
        self._pg_poll_interval = pg_poll_interval
        self._health_wait_timeout = health_wait_timeout
        self._health_poll_interval = health_poll_interval
        self._sleep = sleep

    def run(self, plan: BackendPlan) -> InstanceRef:
        # `docker inspect <name>` exits 0 for a container in ANY state
        # (running or stopped) and only non-zero when the name doesn't exist
        # at all — so a single `_container_exists` check already covers both
        # "running" and "stopped" for the refuse-if-exists gate; no separate
        # running-vs-stopped branch is needed here.
        if self._container_exists(plan.postgres.name) or self._container_exists(plan.odoo.name):
            raise InstanceExistsError(
                f"instance already exists: {plan.network.name} "
                f"(postgres={plan.postgres.name!r}, odoo={plan.odoo.name!r})"
            )

        created: list[_CreatedResource] = []
        try:
            self._ensure_network(plan.network, created)
            for volume in plan.volumes:
                self._ensure_volume(volume, created)

            self._run_container(plan.postgres, created)
            self._wait_pg_ready(plan.postgres)

            self._run_container(plan.odoo, created)
            self._wait_odoo_healthy(plan.odoo)
        except Exception:
            self._rollback(created)
            raise

        return instance_ref(plan)

    # -- resource creation (created-only rollback bookkeeping) --------------

    def _ensure_network(self, spec: NetworkSpec, created: list[_CreatedResource]) -> None:
        if self._network_exists(spec.name):
            return
        self._exec(_network_create_argv(spec))
        created.append(("network", spec.name))

    def _ensure_volume(self, spec: VolumeSpec, created: list[_CreatedResource]) -> None:
        if self._volume_exists(spec.name):
            return
        self._exec(_volume_create_argv(spec))
        created.append(("volume", spec.name))

    def _run_container(self, spec: ContainerSpec, created: list[_CreatedResource]) -> None:
        self._exec(_run_container_argv(spec))
        created.append(("container", spec.name))

    def _rollback(self, created: list[_CreatedResource]) -> None:
        """Tear down ONLY resources this invocation created, in reverse order.

        Best-effort ACROSS EVERY STEP, not just within a single call: each
        teardown is wrapped in its own `try/except Exception: continue` so
        one stuck/failing/timed-out step (e.g. a `docker rm -f -v` that
        raises `DockerUnavailableError` because the daemon died mid-rollback)
        never aborts the remaining teardowns and never masks the original
        `run()` failure that triggered this rollback — that original
        exception is always what `run()` re-raises to the caller, regardless
        of how much of the cleanup below actually succeeds.
        """
        for kind, name in reversed(created):
            try:
                if kind == "container":
                    self._run_raw(["docker", "rm", "-f", "-v", name])
                elif kind == "volume":
                    self._run_raw(["docker", "volume", "rm", name])
                elif kind == "network":
                    self._run_raw(["docker", "network", "rm", name])
            except Exception:
                continue

    # -- readiness gates (injectable clock) ----------------------------------

    def _wait_pg_ready(self, spec: ContainerSpec) -> None:
        user = spec.env["POSTGRES_USER"]
        db = spec.env["POSTGRES_DB"]
        argv = ["docker", "exec", spec.name, "pg_isready", "-h", "127.0.0.1", "-U", user, "-d", db]

        attempts = max(1, int(self._pg_readiness_timeout / self._pg_poll_interval))
        for attempt in range(attempts):
            result = self._run_raw(argv)
            if result.returncode == 0:
                return
            if attempt < attempts - 1:
                self._sleep(self._pg_poll_interval)

        raise PostgresReadinessError(
            f"postgres container {spec.name!r} did not become TCP-ready "
            f"within {self._pg_readiness_timeout}s"
        )

    def _wait_odoo_healthy(self, spec: ContainerSpec) -> None:
        argv = ["docker", "inspect", spec.name]

        attempts = max(1, int(self._health_wait_timeout / self._health_poll_interval))
        for attempt in range(attempts):
            result = self._run_raw(argv)
            if result.returncode == 0 and _health_status(result.stdout) == "healthy":
                return
            if attempt < attempts - 1:
                self._sleep(self._health_poll_interval)

        raise ContainerRunError(
            f"odoo container {spec.name!r} did not become healthy "
            f"within {self._health_wait_timeout}s"
        )

    # -- existence checks -----------------------------------------------------

    def _network_exists(self, name: str) -> bool:
        return self._exists(["docker", "network", "inspect", name])

    def _volume_exists(self, name: str) -> bool:
        return self._exists(["docker", "volume", "inspect", name])

    def _container_exists(self, name: str) -> bool:
        return self._exists(["docker", "inspect", name])

    def _exists(self, argv: list[str]) -> bool:
        result = self._run_raw(argv)
        if result.returncode == 0:
            return True
        if _DAEMON_DOWN_MARKER in (result.stderr or ""):
            raise DockerUnavailableError((result.stderr or "").strip())
        return False

    # -- subprocess boundary --------------------------------------------------

    def _run_raw(self, argv: list[str]) -> subprocess.CompletedProcess:
        """Run `argv`, raising only for a missing binary or a timed-out call.

        Never raises on a nonzero exit code — callers interpret the return
        code themselves (existence checks, readiness polls, rollback).
        """
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._docker_timeout,
                env=_docker_env(),
            )
        except FileNotFoundError as exc:
            raise DockerUnavailableError(f"docker executable not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            # A `docker` CLI call that never returns within `_docker_timeout`
            # means the daemon isn't responding to this invocation — the same
            # underlying failure mode as "daemon unreachable", so
            # `DockerUnavailableError` is the correct classification (mirrors
            # `git_provider`/`workspace/provider`, which both map a subprocess
            # timeout to their own "unavailable"-shaped domain error).
            raise DockerUnavailableError(
                f"docker command timed out after {self._docker_timeout}s: {argv!r}"
            ) from exc

    def _exec(self, argv: list[str]) -> subprocess.CompletedProcess:
        """Run `argv`, classifying a nonzero exit into a typed `BackendError`."""
        result = self._run_raw(argv)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if _DAEMON_DOWN_MARKER in stderr:
                raise DockerUnavailableError(stderr)
            if _IMAGE_NOT_FOUND_MARKER in stderr:
                raise ImageNotFoundError(stderr)
            raise ContainerRunError(stderr or f"docker command failed: {argv!r}")
        return result


__all__ = ["DockerBackendProvider"]
