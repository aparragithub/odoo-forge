"""Concrete `BackendProvider` adapter backed by the `docker` CLI.

Structurally satisfies `odoo_forge.ports.backend_provider.BackendProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `docker` (mirrors
`odoo_forge_git.git_provider`).

This module (PR-2a-i of the Slice 4b chain) implements ONLY the standalone
building blocks: pure argv builders, the subprocess boundary, and error
classification / existence checks. `run()` orchestration and created-only
rollback land in PR-2a-ii.
"""

import json
import os
import subprocess

from odoo_forge.backend.errors import ContainerRunError, DockerUnavailableError, ImageNotFoundError
from odoo_forge.backend.plan import ContainerRole, ContainerSpec, NetworkSpec, VolumeSpec

DEFAULT_DOCKER_TIMEOUT_SECONDS = 30.0

_DAEMON_DOWN_MARKER = "Cannot connect to the Docker daemon"
_IMAGE_NOT_FOUND_MARKER = "Unable to find image"

_ROLE_VOLUME_TARGET: dict[ContainerRole, str] = {
    "postgres": "/var/lib/postgresql/data",
    "odoo": "/var/lib/odoo",
}


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
    """Adapter that maps `BackendPlan` specs to `docker` CLI invocations.

    PR-2a-i: subprocess boundary, error classification, and existence
    checks only. `run()` orchestration and created-only rollback land in
    PR-2a-ii — this class does not yet satisfy the full `BackendProvider`
    Protocol.
    """

    def __init__(self, *, docker_timeout: float = DEFAULT_DOCKER_TIMEOUT_SECONDS) -> None:
        self._docker_timeout = docker_timeout

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
        """Run `argv`, raising only for a missing `docker` binary.

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
