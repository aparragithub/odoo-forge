"""Concrete `BackendProvider` adapter backed by the `docker` CLI.

Structurally satisfies `odoo_forge.ports.backend_provider.BackendProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `docker` (mirrors
`odoo_forge_git.git_provider`).

This module implements the full `run()` orchestration (PR-2a-ii): pure argv
builders, the subprocess boundary, explicit image pull ownership, error
classification, existence checks (PR-2a-i), plus readiness gates and
created-only rollback (PR-2a-ii). PR-2b adds `status()`/`stop()`/`logs()`/
`exec()`, completing all five `BackendProvider` port methods.
"""

import json
import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from odoo_forge.backend.errors import (
    ContainerRunError,
    DockerUnavailableError,
    ImageAuthorizationError,
    ImageNotFoundError,
    InstanceExistsError,
    InstanceNotFoundError,
    PostgresReadinessError,
)
from odoo_forge.backend.plan import (
    BackendPlan,
    ContainerRole,
    ContainerSpec,
    NetworkSpec,
    VolumeSpec,
)
from odoo_forge.backend.status import (
    ExecResult,
    InstanceRef,
    InstanceStatus,
    instance_ref,
    parse_status,
)
from odoo_forge.credentials.errors import CredentialError
from odoo_forge_docker.credential_injection import SopsEnvFileInjector

DEFAULT_DOCKER_TIMEOUT_SECONDS = 30.0
DEFAULT_PG_READINESS_TIMEOUT_SECONDS = 30.0
DEFAULT_PG_POLL_INTERVAL_SECONDS = 1.0
# Two complete 150s health-failure envelopes permit one recovery window.
DEFAULT_HEALTH_WAIT_TIMEOUT_SECONDS = 300.0
DEFAULT_HEALTH_POLL_INTERVAL_SECONDS = 5.0
_BOOTSTRAP_TIMEOUT_SECONDS = 300.0

_DAEMON_DOWN_MARKER = "Cannot connect to the Docker daemon"
_IMAGE_NOT_FOUND_MARKER = "Unable to find image"
_PULL_IMAGE_NOT_FOUND_MARKERS = (
    "unable to find image",
    "manifest unknown",
    "not found",
    "does not exist",
)
_PULL_AUTH_MARKERS = (
    "pull access denied",
    "unauthorized",
    "authentication required",
    "denied",
)
_BOOTSTRAP_OUTPUT_LIMIT = 8_000

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


def _run_container_argv(
    spec: ContainerSpec, secret_files: Path | Mapping[str, Path] | None = None
) -> list[str]:
    argv = ["docker", "run", "-d", "--name", spec.name, "--network", spec.network]
    for key, value in spec.labels.items():
        argv += ["--label", f"{key}={value}"]
    if isinstance(secret_files, Path):
        argv += ["--env-file", str(secret_files)]
    elif secret_files is not None:
        for key, path in secret_files.items():
            target = f"/run/secrets/{key}"
            argv += ["--mount", f"type=bind,source={path},target={target},readonly"]
            argv += ["-e", f"{key}_FILE={target}"]
    for key, value in spec.env.items():
        argv += ["-e", f"{key}={value}"]
    target = _ROLE_VOLUME_TARGET[spec.role]
    for volume in spec.volumes:
        argv += ["-v", f"{volume.name}:{target}"]
    for mount in spec.mounts:
        suffix = ":ro" if mount.read_only else ""
        argv += ["-v", f"{mount.host_path}:{mount.container_path}{suffix}"]
    for container_port, host_port in spec.ports.items():
        host = "127.0.0.1:0" if host_port is None else f"127.0.0.1:{host_port}"
        argv += ["-p", f"{host}:{container_port}"]
    argv.append(spec.image)
    return argv


def _bootstrap_container_argv(
    spec: ContainerSpec,
    secret_files: Path | Mapping[str, Path] | None = None,
    cidfile: Path | None = None,
) -> list[str]:
    """Build the foreground, portless base-schema initialization command."""
    argv = _run_container_argv(spec.model_copy(update={"ports": {}}), secret_files)
    argv.remove("-d")
    if cidfile is not None:
        argv[2:2] = ["--cidfile", str(cidfile)]
    return [*argv, "-i", "base", "--stop-after-init", "--no-http"]


def _pull_image_argv(spec: ContainerSpec) -> list[str]:
    return ["docker", "pull", spec.image]


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


def _planned_env_values(plan: BackendPlan) -> tuple[str, ...]:
    return (*plan.postgres.env.values(), *plan.odoo.env.values())


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
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        credential_injector: SopsEnvFileInjector | None = None,
    ) -> None:
        self._docker_timeout = docker_timeout
        self._pg_readiness_timeout = pg_readiness_timeout
        self._pg_poll_interval = pg_poll_interval
        self._health_wait_timeout = health_wait_timeout
        self._health_poll_interval = health_poll_interval
        self._monotonic = monotonic
        self._sleep = sleep
        self._credential_injector = credential_injector or SopsEnvFileInjector()

    def run(self, plan: BackendPlan) -> InstanceRef:
        # `docker inspect <name>` exits 0 for a container in ANY state
        # (running or stopped) and only non-zero when the name doesn't exist
        # at all — so a single `_container_exists` check already covers both
        # "running" and "stopped" for the refuse-if-exists gate; no separate
        # running-vs-stopped branch is needed here.
        try:
            self._credential_injector.validate(plan.postgres)
            self._credential_injector.validate(plan.odoo)
        except CredentialError as exc:
            raise ContainerRunError("credential injection failed") from exc

        bootstrap = plan.odoo.model_copy(update={"name": f"{plan.odoo.name}-bootstrap"})
        if (
            self._container_exists(plan.postgres.name)
            or self._container_exists(plan.odoo.name)
            or self._container_exists(bootstrap.name)
        ):
            raise InstanceExistsError(
                f"instance already exists: {plan.network.name} "
                f"(postgres={plan.postgres.name!r}, odoo={plan.odoo.name!r}, "
                f"bootstrap={bootstrap.name!r})"
            )

        created: list[_CreatedResource] = []
        try:
            self._pull_image(plan.odoo)
            self._ensure_network(plan.network, created)
            pgdata_created = self._ensure_volume(plan.postgres.volumes[0], created)
            for volume in plan.volumes:
                if volume.name != plan.postgres.volumes[0].name:
                    self._ensure_volume(volume, created)

            self._run_container(plan.postgres, created)
            self._wait_pg_ready(plan.postgres)

            if pgdata_created:
                self._run_bootstrap(bootstrap, _planned_env_values(plan), created)
                bootstrap_resource = created[-1]
                self._exec(["docker", "rm", "-f", "-v", bootstrap_resource[1]])
                created.remove(bootstrap_resource)

            self._run_container(plan.odoo, created)
            self._wait_odoo_healthy(plan.odoo)
        except Exception as exc:
            detail = str(exc)
            if isinstance(exc, ContainerRunError) and "did not become healthy" in detail:
                detail = (
                    f"odoo readiness timed out after {self._health_wait_timeout:g}s; "
                    f"{self._readiness_diagnostics(plan.odoo, _planned_env_values(plan))}"
                )
            residuals = self._rollback(created)
            if residuals:
                detail = f"{detail}; cleanup incomplete: {', '.join(residuals)}"
            if detail != str(exc):
                raise exc.__class__(detail) from exc
            raise
        finally:
            self._credential_injector.clear()

        return instance_ref(plan)

    # -- status/stop/logs/exec (PR-2b) ---------------------------------------

    def status(self, ref: InstanceRef) -> InstanceStatus:
        """Report `ref`'s live state without ever raising for an absent instance.

        `docker inspect` both role containers in a single call. A missing
        container makes `docker inspect` exit non-zero while still printing
        JSON for whichever names DO exist (or `[]` if none do) — this method
        ignores the exit code and hands whatever JSON was decoded straight to
        `parse_status`, which already treats absent/empty entries as
        not-running without raising (design "Absent/empty inspect").
        """
        result = self._run_raw(["docker", "inspect", ref.postgres_container, ref.odoo_container])
        stderr = (result.stderr or "").strip()
        if _DAEMON_DOWN_MARKER in stderr:
            raise DockerUnavailableError(stderr)
        try:
            data = json.loads(result.stdout) if result.stdout else []
        except (ValueError, TypeError):
            data = []
        return parse_status(data)

    def stop(self, ref: InstanceRef) -> None:
        """Stop and remove both role containers plus the network.

        Named PG-data/filestore volumes are deliberately NEVER passed to
        `docker volume rm` here, preserving instance state across a
        `stop` -> `run` cycle (design "stop semantics"). Raises
        `InstanceNotFoundError` when NEITHER role container exists.
        """
        pg_exists = self._container_exists(ref.postgres_container)
        odoo_exists = self._container_exists(ref.odoo_container)
        if not pg_exists and not odoo_exists:
            raise InstanceNotFoundError(
                f"no managed containers found for instance {ref.instance!r}"
            )

        for name, exists in (
            (ref.postgres_container, pg_exists),
            (ref.odoo_container, odoo_exists),
        ):
            if not exists:
                continue
            self._exec(["docker", "stop", name])
            self._exec(["docker", "rm", "-f", "-v", name])

        if self._network_exists(ref.network):
            self._exec(["docker", "network", "rm", ref.network])

    def logs(self, ref: InstanceRef, role: ContainerRole) -> str:
        """Return `role`'s captured `docker logs` output for `ref`."""
        name = ref.postgres_container if role == "postgres" else ref.odoo_container
        if not self._container_exists(name):
            raise InstanceNotFoundError(f"container not found for role {role!r}: {name!r}")
        result = self._exec(["docker", "logs", name])
        return result.stdout

    def exec(self, ref: InstanceRef, argv: Sequence[str]) -> ExecResult:
        """Run `argv` inside `ref`'s Odoo container and return its result.

        A non-zero exit code is NOT an exception here — the caller inspects
        `ExecResult.exit_code` themselves, mirroring `subprocess`'s own
        `check=False` contract.
        """
        name = ref.odoo_container
        if not self._container_exists(name):
            raise InstanceNotFoundError(f"odoo container not found: {name!r}")
        result = self._run_raw(["docker", "exec", name, *argv])
        return ExecResult(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)

    # -- resource creation (created-only rollback bookkeeping) --------------

    def _ensure_network(self, spec: NetworkSpec, created: list[_CreatedResource]) -> None:
        if self._network_exists(spec.name):
            return
        self._exec(_network_create_argv(spec))
        created.append(("network", spec.name))

    def _ensure_volume(self, spec: VolumeSpec, created: list[_CreatedResource]) -> bool:
        if self._volume_exists(spec.name):
            return False
        ownership = uuid.uuid4().hex
        owned_spec = spec.model_copy(
            update={"labels": {**spec.labels, "com.odoo-forge.create-token": ownership}}
        )
        self._exec(_volume_create_argv(owned_spec))
        if not self._volume_has_label(spec.name, "com.odoo-forge.create-token", ownership):
            raise ContainerRunError(f"volume ownership verification failed: {spec.name!r}")
        created.append(("volume", spec.name))
        return True

    def _run_container(self, spec: ContainerSpec, created: list[_CreatedResource]) -> None:
        if spec.secret_env:
            with self._credential_injector.secret_files(spec) as secret_files:
                self._exec(_run_container_argv(spec, secret_files))
        else:
            self._exec(_run_container_argv(spec))
        created.append(("container", spec.name))

    def _run_bootstrap(
        self,
        spec: ContainerSpec,
        planned_env_values: Sequence[str],
        created: list[_CreatedResource],
    ) -> None:
        """Initialize Odoo base only for PG data owned by this invocation."""
        with tempfile.TemporaryDirectory(prefix="odoo-forge-bootstrap-") as directory:
            cidfile = Path(directory) / "container.cid"
            try:
                if spec.secret_env:
                    with self._credential_injector.secret_files(spec) as secret_files:
                        result = self._run_raw(
                            _bootstrap_container_argv(spec, secret_files, cidfile),
                            timeout=_BOOTSTRAP_TIMEOUT_SECONDS,
                        )
                else:
                    result = self._run_raw(
                        _bootstrap_container_argv(spec, cidfile=cidfile),
                        timeout=_BOOTSTRAP_TIMEOUT_SECONDS,
                    )
            except Exception as exc:
                self._record_bootstrap_identity(cidfile, created)
                raise ContainerRunError(
                    f"bootstrap failed; {self._readiness_diagnostics(spec, planned_env_values)}"
                ) from exc

            if not self._record_bootstrap_identity(cidfile, created):
                raise ContainerRunError("bootstrap failed: safe container identity unavailable")

        if result.returncode == 0:
            return
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)[
            -_BOOTSTRAP_OUTPUT_LIMIT:
        ]
        raise ContainerRunError(
            f"bootstrap failed with exit code {result.returncode}; "
            f"output={self._redact(output, planned_env_values)}; "
            f"{self._readiness_diagnostics(spec, planned_env_values)}"
        )

    @staticmethod
    def _record_bootstrap_identity(cidfile: Path, created: list[_CreatedResource]) -> bool:
        try:
            container_id = cidfile.read_text().strip()
        except OSError:
            return False
        if not container_id:
            return False
        created.append(("container", container_id))
        return True

    def _pull_image(self, spec: ContainerSpec) -> None:
        """Pull the planned image before container start and classify failures.

        Pull stderr is normalized here so the CLI can keep a single
        `error: ...` boundary while still preserving pull failure classes.
        """
        result = self._run_raw(_pull_image_argv(spec))
        if result.returncode == 0:
            return

        stderr = " ".join((result.stderr or "").split())
        lowered = stderr.lower()
        if _DAEMON_DOWN_MARKER in stderr:
            raise DockerUnavailableError(stderr)
        if any(marker in lowered for marker in _PULL_AUTH_MARKERS):
            raise ImageAuthorizationError(
                stderr or f"authorization denied while pulling {spec.image!r}"
            )
        if any(marker in lowered for marker in _PULL_IMAGE_NOT_FOUND_MARKERS):
            raise ImageNotFoundError(stderr or f"image not found: {spec.image!r}")
        raise ContainerRunError(stderr or f"docker pull failed for {spec.image!r}")

    def _rollback(self, created: list[_CreatedResource]) -> list[str]:
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
        residuals: list[str] = []
        for kind, name in reversed(created):
            try:
                if kind == "container":
                    argv = ["docker", "rm", "-f", "-v", name]
                elif kind == "volume":
                    argv = ["docker", "volume", "rm", name]
                elif kind == "network":
                    argv = ["docker", "network", "rm", name]
                else:
                    continue
                result = self._run_raw(argv)
                if result.returncode != 0:
                    residuals.append(f"{kind}={name}")
            except Exception:
                residuals.append(f"{kind}={name}")
        return residuals

    # -- readiness gates (injectable clock) ----------------------------------

    def _wait_pg_ready(self, spec: ContainerSpec) -> None:
        user = spec.env["POSTGRES_USER"]
        db = spec.env["POSTGRES_DB"]
        argv = ["docker", "exec", spec.name, "pg_isready", "-h", "127.0.0.1", "-U", user, "-d", db]

        if self._wait_until(
            lambda timeout: self._run_raw(argv, timeout=timeout).returncode == 0,
            self._pg_readiness_timeout,
            self._pg_poll_interval,
        ):
            return

        raise PostgresReadinessError(
            f"postgres container {spec.name!r} did not become TCP-ready "
            f"within {self._pg_readiness_timeout}s"
        )

    def _wait_odoo_healthy(self, spec: ContainerSpec) -> None:
        argv = ["docker", "inspect", spec.name]

        def healthy(timeout: float) -> bool:
            result = self._run_raw(argv, timeout=timeout)
            return result.returncode == 0 and _health_status(result.stdout) == "healthy"

        if self._wait_until(healthy, self._health_wait_timeout, self._health_poll_interval):
            return

        raise ContainerRunError(
            f"odoo container {spec.name!r} did not become healthy "
            f"within {self._health_wait_timeout}s"
        )

    def _readiness_diagnostics(self, spec: ContainerSpec, planned_env_values: Sequence[str]) -> str:
        """Capture selected, redacted Odoo timeout evidence before rollback."""
        final_health = "unknown"
        inspect = "unavailable"
        try:
            result = self._run_raw(["docker", "inspect", spec.name])
            if result.returncode == 0:
                payload = json.loads(result.stdout)
                state = payload[0]["State"]
                health = state.get("Health", {})
                final_health = health.get("Status", "unknown")
                selected = {
                    key: state[key]
                    for key in ("Status", "Running", "ExitCode", "Error", "OOMKilled")
                    if key in state
                }
                if isinstance(health, dict):
                    selected["Health"] = {
                        key: health[key] for key in ("Status", "FailingStreak") if key in health
                    }
                inspect = json.dumps(selected, sort_keys=True)
        except Exception:
            pass

        logs = "unavailable"
        try:
            result = self._run_raw(["docker", "logs", "--tail", "200", spec.name])
            if result.returncode == 0:
                logs = "\n".join(part for part in (result.stdout, result.stderr) if part)
        except Exception:
            pass

        return (
            f"final_health={final_health}; inspect={self._redact(inspect, planned_env_values)}; "
            f"logs={self._redact(logs, planned_env_values)}"
        )

    def _redact(self, value: str, planned_env_values: Sequence[str]) -> str:
        return self._credential_injector.redact(value, planned_env_values)

    def _wait_until(
        self, probe: Callable[[float], bool], timeout: float, poll_interval: float
    ) -> bool:
        """Poll within one monotonic deadline, including probe and sleep time."""
        deadline = self._monotonic() + max(0.0, timeout)
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0.0:
                return False
            if probe(min(self._docker_timeout, remaining)):
                return True
            remaining = deadline - self._monotonic()
            if remaining <= 0.0:
                return False
            self._sleep(min(poll_interval, remaining))

    # -- existence checks -----------------------------------------------------

    def _network_exists(self, name: str) -> bool:
        return self._exists(["docker", "network", "inspect", name])

    def _volume_exists(self, name: str) -> bool:
        return self._exists(["docker", "volume", "inspect", name])

    def _volume_has_label(self, name: str, key: str, value: str) -> bool:
        result = self._run_raw(["docker", "volume", "inspect", name])
        if result.returncode != 0:
            return False
        try:
            labels = json.loads(result.stdout)[0].get("Labels") or {}
        except (ValueError, TypeError, IndexError, AttributeError):
            return False
        return labels.get(key) == value

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

    def _run_raw(
        self, argv: list[str], *, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
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
                timeout=self._docker_timeout if timeout is None else timeout,
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
                f"docker command timed out after "
                f"{self._docker_timeout if timeout is None else timeout}s: {argv!r}"
            ) from exc

    def _exec(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
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
