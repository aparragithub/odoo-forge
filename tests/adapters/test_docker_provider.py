import inspect
import json
import stat
import subprocess
import typing
from pathlib import Path

import pytest

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
    Mount,
    NetworkSpec,
    VolumeSpec,
)
from odoo_forge.backend.status import ExecResult, InstanceRef, InstanceStatus
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.ports.backend_provider import BackendProvider
from odoo_forge_docker.credential_injection import SopsCommandResolver, SopsEnvFileInjector
from odoo_forge_docker.provider import (
    DockerBackendProvider,
    _docker_env,
    _health_status,
    _network_create_argv,
    _run_container_argv,
    _volume_create_argv,
)

NETWORK = "odoo-forge-proj-default"
DB_NAME = "odoo-forge-proj-default-db"
ODOO_NAME = "odoo-forge-proj-default-odoo"
PGDATA_VOL = "odoo-forge-proj-default-pgdata"
FILESTORE_VOL = "odoo-forge-proj-default-filestore"


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _labels(role: str | None = None) -> dict[str, str]:
    labels = {
        "com.odoo-forge.project": "proj",
        "com.odoo-forge.instance": "default",
        "com.odoo-forge.managed": "true",
    }
    if role is not None:
        labels["com.odoo-forge.role"] = role
    return labels


def _fake_daemon_down(argv: list[str], **kwargs: object) -> "_FakeCompletedProcess":
    return _FakeCompletedProcess(
        1, stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
    )


def _make_postgres_spec() -> ContainerSpec:
    volume = VolumeSpec(name=PGDATA_VOL, labels=_labels("postgres"))
    return ContainerSpec(
        name=DB_NAME,
        image="postgres:16",
        role="postgres",
        network=NETWORK,
        env={"POSTGRES_PASSWORD": "odoo", "POSTGRES_USER": "odoo", "POSTGRES_DB": "proj"},
        mounts=[],
        labels=_labels("postgres"),
        volumes=[volume],
        ports={},
    )


def _make_plan() -> BackendPlan:
    network = NetworkSpec(name=NETWORK, labels=_labels())
    pg_volume = VolumeSpec(name=PGDATA_VOL, labels=_labels("postgres"))
    fs_volume = VolumeSpec(name=FILESTORE_VOL, labels=_labels("odoo"))
    postgres = ContainerSpec(
        name=DB_NAME,
        image="postgres:16",
        role="postgres",
        network=NETWORK,
        env={"POSTGRES_PASSWORD": "odoo", "POSTGRES_USER": "odoo", "POSTGRES_DB": "proj"},
        mounts=[],
        labels=_labels("postgres"),
        volumes=[pg_volume],
        ports={},
    )
    odoo = ContainerSpec(
        name=ODOO_NAME,
        image="odoo-forge-odoo:19.0",
        role="odoo",
        network=NETWORK,
        env={
            "DB_HOST": DB_NAME,
            "DB_PORT": "5432",
            "DB_USER": "odoo",
            "DB_PASSWORD": "odoo",
            "POSTGRES_DB": "proj",
        },
        mounts=[],
        labels=_labels("odoo"),
        volumes=[fs_volume],
        ports={"8069": None, "8072": None},
    )
    return BackendPlan(
        network=network, volumes=[pg_volume, fs_volume], postgres=postgres, odoo=odoo
    )


def _make_digest_plan() -> BackendPlan:
    plan = _make_plan()
    digest_ref = "ghcr.io/odoo/odoo@sha256:" + "b" * 64
    return plan.model_copy(update={"odoo": plan.odoo.model_copy(update={"image": digest_ref})})


def _healthy_inspect(_name: str) -> str:
    return json.dumps([{"State": {"Running": True, "Health": {"Status": "healthy"}}}])


def _make_ref() -> InstanceRef:
    return InstanceRef(
        project="proj",
        instance="default",
        network=NETWORK,
        postgres_container=DB_NAME,
        odoo_container=ODOO_NAME,
    )


def _inspect_entry(role: str, running: bool, health: str | None) -> dict[str, object]:
    state: dict[str, object] = {"Running": running}
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Config": {"Labels": {"com.odoo-forge.role": role}},
        "State": state,
    }


class _Router:
    """Dispatches fake `docker` argv to canned responses, recording every call."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []
        self.not_found: set[str] = set()
        self.pull_error_stderr: str | None = None
        self.pg_ready_after: int = 0
        self._pg_attempts = 0
        self.odoo_healthy_after: int = 0
        self._odoo_attempts = 0
        self._created_containers: set[str] = set()

    def __call__(self, argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        self.calls.append(list(argv))
        self.kwargs.append(kwargs)

        if argv[1:3] == ["network", "inspect"]:
            name = argv[3]
            return _FakeCompletedProcess(1 if name in self.not_found else 0)
        if argv[1:3] == ["volume", "inspect"]:
            name = argv[3]
            return _FakeCompletedProcess(1 if name in self.not_found else 0)
        if argv[1] == "inspect" and len(argv) == 3:
            name = argv[2]
            if name not in self._created_containers:
                # Pre-creation existence check (precheck): only "exists" if
                # NOT in `not_found` — used for the run() refuse-if-exists gate.
                return _FakeCompletedProcess(1 if name in self.not_found else 0)
            if name == ODOO_NAME:
                self._odoo_attempts += 1
                if self._odoo_attempts > self.odoo_healthy_after:
                    return _FakeCompletedProcess(0, stdout=_healthy_inspect(name))
                return _FakeCompletedProcess(
                    0,
                    stdout=json.dumps(
                        [{"State": {"Running": True, "Health": {"Status": "starting"}}}]
                    ),
                )
            return _FakeCompletedProcess(0, stdout=json.dumps([{"State": {"Running": True}}]))
        if argv[1:3] == ["network", "create"]:
            return _FakeCompletedProcess(0)
        if argv[1:3] == ["volume", "create"]:
            return _FakeCompletedProcess(0)
        if argv[1] == "pull":
            if self.pull_error_stderr is not None:
                return _FakeCompletedProcess(1, stderr=self.pull_error_stderr)
            return _FakeCompletedProcess(0)
        if argv[1] == "run":
            name = argv[argv.index("--name") + 1]
            self._created_containers.add(name)
            return _FakeCompletedProcess(0, stdout="container-id")
        if argv[1] == "exec" and "pg_isready" in argv:
            self._pg_attempts += 1
            if self._pg_attempts > self.pg_ready_after:
                return _FakeCompletedProcess(0)
            return _FakeCompletedProcess(2, stderr="no response")
        if argv[1] == "logs":
            return _FakeCompletedProcess(0, stdout="readiness diagnostics")
        if argv[1:3] == ["rm", "-f"] or (argv[1] == "rm" and "-f" in argv):
            return _FakeCompletedProcess(0)
        if argv[1:3] == ["volume", "rm"]:
            return _FakeCompletedProcess(0)
        if argv[1:3] == ["network", "rm"]:
            return _FakeCompletedProcess(0)
        raise AssertionError(f"unexpected docker invocation: {argv}")


def _make_router(**kwargs: object) -> _Router:
    router = _Router()
    for key, value in kwargs.items():
        setattr(router, key, value)
    return router


# -- pure argv builders / env -------------------------------------------------


def test_network_create_argv_includes_labels_and_name() -> None:
    spec = NetworkSpec(name=NETWORK, labels=_labels())
    argv = _network_create_argv(spec)

    assert argv[:3] == ["docker", "network", "create"]
    assert argv[-1] == NETWORK
    assert "--label" in argv
    assert f"com.odoo-forge.project={_labels()['com.odoo-forge.project']}" in argv


def test_volume_create_argv_includes_labels_and_name() -> None:
    spec = VolumeSpec(name=PGDATA_VOL, labels=_labels("postgres"))
    argv = _volume_create_argv(spec)

    assert argv[:3] == ["docker", "volume", "create"]
    assert argv[-1] == PGDATA_VOL
    assert "com.odoo-forge.role=postgres" in argv


def test_run_container_argv_includes_network_env_volumes_ports() -> None:
    argv = _run_container_argv(_make_postgres_spec())

    assert argv[:2] == ["docker", "run"]
    assert "--name" in argv and DB_NAME in argv and "--network" in argv and NETWORK in argv
    assert "-e" in argv and "POSTGRES_USER=odoo" in argv
    assert "-v" in argv and f"{PGDATA_VOL}:/var/lib/postgresql/data" in argv
    assert argv[-1] == "postgres:16"


def test_sops_env_file_injector_writes_mode_0600_and_cleans_up() -> None:
    secret = "credential-value-not-for-argv"
    spec = _make_postgres_spec().model_copy(
        update={
            "env": {
                "POSTGRES_USER": "odoo",
                "POSTGRES_DB": "proj",
            },
            "secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://postgres-password")},
        }
    )
    injector = SopsEnvFileInjector(resolver=lambda _handle: secret)

    with injector.env_file(spec) as env_file:
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
        assert env_file.read_text() == f"POSTGRES_PASSWORD={secret}\n"

    assert not env_file.exists()


def test_sops_env_file_injector_cleans_up_when_docker_launch_fails() -> None:
    spec = _make_postgres_spec().model_copy(
        update={"secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://postgres-password")}}
    )
    injector = SopsEnvFileInjector(resolver=lambda _handle: "credential-value-not-for-argv")

    with pytest.raises(RuntimeError), injector.env_file(spec) as env_file:
        assert env_file.exists()
        raise RuntimeError("docker launch failed")

    assert not env_file.exists()


def test_sops_secret_file_cleanup_preserves_the_write_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "credentials"
    directory.mkdir()
    monkeypatch.setattr(
        "odoo_forge_docker.credential_injection.tempfile.mkdtemp", lambda **_: str(directory)
    )

    def fail_chmod(_path: Path, _mode: int) -> None:
        raise OSError("chmod failed")

    monkeypatch.setattr("odoo_forge_docker.credential_injection.os.chmod", fail_chmod)
    spec = _make_postgres_spec().model_copy(
        update={"secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://postgres-password")}}
    )

    with (
        pytest.raises(OSError, match="chmod failed"),
        SopsEnvFileInjector(resolver=lambda _handle: "credential-value").secret_files(spec),
    ):
        pass

    assert not directory.exists()


def test_sops_command_resolver_invokes_the_configured_document_without_a_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    credentials_file = tmp_path / "project" / "credentials.sops.yaml"
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="resolved-value\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    resolver = SopsCommandResolver(credentials_file)
    value = resolver(CredentialHandle("local-backend/postgres-password"))

    assert value == "resolved-value"
    assert calls == [
        (
            [
                "sops",
                "--decrypt",
                "--extract",
                '["local-backend/postgres-password"]',
                str(credentials_file),
            ],
            {"capture_output": True, "text": True, "check": False},
        )
    ]


def test_run_container_argv_uses_env_file_without_secret_values() -> None:
    secret = "credential-value-not-for-argv"
    spec = _make_postgres_spec().model_copy(
        update={"env": {"POSTGRES_USER": "odoo", "POSTGRES_DB": "proj"}}
    )

    argv = _run_container_argv(spec, Path("/tmp/credential.env"))

    assert "--env-file" in argv
    assert "/tmp/credential.env" in argv
    assert f"POSTGRES_PASSWORD={secret}" not in argv
    assert secret not in " ".join(argv)


def test_provider_uses_secret_files_and_removes_secrets_from_subprocess_observables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "credential-value-not-for-argv"
    plan = _make_plan().model_copy(
        update={
            "postgres": _make_plan().postgres.model_copy(
                update={
                    "env": {"POSTGRES_USER": "odoo", "POSTGRES_DB": "proj"},
                    "secret_env": {
                        "POSTGRES_PASSWORD": CredentialHandle("sops://postgres-password")
                    },
                }
            ),
            "odoo": _make_plan().odoo.model_copy(
                update={
                    "env": {
                        "DB_HOST": DB_NAME,
                        "DB_PORT": "5432",
                        "DB_USER": "odoo",
                        "POSTGRES_DB": "proj",
                    },
                    "secret_env": {"DB_PASSWORD": CredentialHandle("sops://odoo-db-password")},
                }
            ),
        }
    )
    router = _make_router(not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    DockerBackendProvider(
        sleep=lambda _seconds: None,
        credential_injector=SopsEnvFileInjector(resolver=lambda _handle: secret),
    ).run(plan)

    secret_file_paths = [
        Path(token.split(",")[1].removeprefix("source="))
        for call in router.calls
        for token in call
        if token.startswith("type=bind,source=") and ",target=/run/secrets/" in token
    ]
    assert len(secret_file_paths) == 2
    assert all(not path.exists() for path in secret_file_paths)
    assert all("--env-file" not in call for call in router.calls)
    assert all(secret not in " ".join(call) for call in router.calls)
    assert all(
        secret not in values.values()
        for kwargs in router.kwargs
        if isinstance((values := kwargs.get("env")), dict)
    )


def test_provider_fails_closed_before_docker_when_sops_resolution_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _make_plan().model_copy(
        update={
            "postgres": _make_plan().postgres.model_copy(
                update={"secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://missing")}}
            )
        }
    )
    router = _make_router()
    monkeypatch.setattr(subprocess, "run", router)

    with pytest.raises(ContainerRunError) as excinfo:
        DockerBackendProvider(sleep=lambda _seconds: None).run(plan)

    assert "sops://missing" not in str(excinfo.value)
    assert router.calls == []


def test_provider_redacts_sops_resolver_diagnostics_before_docker_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "credential-value-not-for-diagnostics"
    plan = _make_plan().model_copy(
        update={
            "postgres": _make_plan().postgres.model_copy(
                update={"secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://broken")}}
            )
        }
    )
    router = _make_router()
    monkeypatch.setattr(subprocess, "run", router)

    def broken_resolver(_handle: CredentialHandle) -> str:
        raise RuntimeError(secret)

    with pytest.raises(ContainerRunError) as excinfo:
        DockerBackendProvider(
            sleep=lambda _seconds: None,
            credential_injector=SopsEnvFileInjector(resolver=broken_resolver),
        ).run(plan)

    assert str(excinfo.value) == "credential injection failed"
    assert secret not in str(excinfo.value)
    assert router.calls == []


def test_run_container_argv_loopback_ports_and_readonly_mount_suffix() -> None:
    """Pins loopback-only dynamic host ports and the read-only mount suffix."""
    spec = ContainerSpec(
        name="odoo-forge-proj-default-odoo",
        image="odoo-forge-odoo:19.0",
        role="odoo",
        network=NETWORK,
        env={},
        mounts=[
            Mount(
                root="worktrees", host_path="/host/worktrees", container_path="/w", read_only=False
            ),
            Mount(root="custom", host_path="/host/custom", container_path="/c", read_only=True),
        ],
        labels=_labels("odoo"),
        volumes=[],
        ports={"8069": None, "8072": None},
    )

    argv = _run_container_argv(spec)

    assert "-p" in argv and "127.0.0.1:0:8069" in argv and "127.0.0.1:0:8072" in argv
    assert "/host/worktrees:/w" in argv
    assert "/host/worktrees:/w:ro" not in argv
    assert "/host/custom:/c:ro" in argv


def test_run_container_argv_binds_published_ports_to_loopback() -> None:
    argv = _run_container_argv(_make_plan().odoo)

    assert "127.0.0.1:0:8069" in argv
    assert "127.0.0.1:0:8072" in argv


def test_run_container_argv_uses_secret_files_not_container_environment() -> None:
    secret = "credential-value-not-in-docker-config"
    spec = _make_postgres_spec().model_copy(
        update={
            "env": {"POSTGRES_USER": "odoo", "POSTGRES_DB": "proj"},
            "secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://postgres-password")},
        }
    )

    argv = _run_container_argv(
        spec,
        {"POSTGRES_PASSWORD": Path("/tmp/credential-file")},
    )

    assert "--env-file" not in argv
    assert secret not in " ".join(argv)
    assert "POSTGRES_PASSWORD=" not in argv
    assert "POSTGRES_PASSWORD_FILE=/run/secrets/POSTGRES_PASSWORD" in argv
    assert any(
        token == "type=bind,source=/tmp/credential-file,"
        "target=/run/secrets/POSTGRES_PASSWORD,readonly"
        for token in argv
    )


def test_docker_env_pins_lang_and_lc_all_to_c() -> None:
    env = _docker_env()

    assert env["LANG"] == "C"
    assert env["LC_ALL"] == "C"


# -- _health_status pure helper -----------------------------------------------


def test_health_status_parses_healthy_and_rejects_invalid_json() -> None:
    stdout = json.dumps([{"State": {"Running": True, "Health": {"Status": "healthy"}}}])

    assert _health_status(stdout) == "healthy"
    assert _health_status("not json") is None


# -- existence checks -----------------------------------------------------


def test_container_exists_true_and_false(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _Router()
    monkeypatch.setattr(subprocess, "run", router)
    provider = DockerBackendProvider()

    assert provider._container_exists(DB_NAME) is True
    assert router.calls[0] == ["docker", "inspect", DB_NAME]

    router.not_found = {DB_NAME}
    assert provider._container_exists(DB_NAME) is False


def test_network_and_volume_exists_dispatch_to_correct_inspect_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _Router()
    monkeypatch.setattr(subprocess, "run", router)
    provider = DockerBackendProvider()

    assert provider._network_exists(NETWORK) is True
    assert router.calls[0] == ["docker", "network", "inspect", NETWORK]

    assert provider._volume_exists(PGDATA_VOL) is True
    assert router.calls[1] == ["docker", "volume", "inspect", PGDATA_VOL]


def test_exists_raises_docker_unavailable_on_daemon_down_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_daemon_down)

    with pytest.raises(DockerUnavailableError):
        DockerBackendProvider()._container_exists(DB_NAME)


# -- error classification: _run_raw / _exec -----------------------------------


def test_run_raw_raises_docker_unavailable_on_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(DockerUnavailableError):
        DockerBackendProvider()._run_raw(["docker", "inspect", DB_NAME])


def test_run_raw_raises_docker_unavailable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors `test_ls_remote_timeout_raises_network_error` / `test_workspace_provider`'s
    equivalent: a `subprocess.TimeoutExpired` must never surface as a raw traceback."""

    def _fake_run(argv: list[str], **kwargs: object) -> None:
        timeout = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(
            cmd=list(argv), timeout=timeout if isinstance(timeout, (int, float)) else 30
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(DockerUnavailableError):
        DockerBackendProvider()._run_raw(["docker", "inspect", DB_NAME])


def test_exec_raises_docker_unavailable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        timeout = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(
            cmd=list(argv), timeout=timeout if isinstance(timeout, (int, float)) else 30
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(DockerUnavailableError):
        DockerBackendProvider()._exec(["docker", "run", "-d", "--name", DB_NAME])


def test_exec_raises_docker_unavailable_on_daemon_down_stderr_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_daemon_down)

    with pytest.raises(DockerUnavailableError):
        DockerBackendProvider()._exec(["docker", "run", "-d", "--name", DB_NAME])


def test_exec_raises_image_not_found_on_stderr_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1, stderr="Unable to find image 'postgres:16' locally")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(ImageNotFoundError):
        DockerBackendProvider()._exec(["docker", "run", "-d", "--name", DB_NAME])


def test_exec_raises_generic_container_run_error_on_other_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1, stderr="some other docker failure")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(ContainerRunError):
        DockerBackendProvider()._exec(["docker", "run", "-d", "--name", DB_NAME])


# -- run() orchestration -------------------------------------------------


def test_run_argv_network_volume_container_order(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(sleep=lambda _seconds: None)
    ref = provider.run(_make_plan())

    assert ref.postgres_container == DB_NAME
    assert ref.odoo_container == ODOO_NAME

    kinds = [tuple(call[:3]) for call in router.calls]
    assert ("docker", "pull", _make_plan().odoo.image) in kinds
    assert ("docker", "inspect", DB_NAME) in kinds
    assert ("docker", "inspect", ODOO_NAME) in kinds
    pull_idx = next(i for i, c in enumerate(router.calls) if c[1] == "pull")
    assert router.calls[kinds.index(("docker", "network", "create"))][:3] == [
        "docker",
        "network",
        "create",
    ]

    network_idx = next(i for i, c in enumerate(router.calls) if c[1:3] == ["network", "create"])
    volume_idxs = [i for i, c in enumerate(router.calls) if c[1:3] == ["volume", "create"]]
    pg_run_idx = next(i for i, c in enumerate(router.calls) if c[1] == "run" and DB_NAME in c)
    pg_ready_idx = next(i for i, c in enumerate(router.calls) if c[1] == "exec")
    odoo_run_idx = next(i for i, c in enumerate(router.calls) if c[1] == "run" and ODOO_NAME in c)

    assert pull_idx < network_idx < min(volume_idxs) < pg_run_idx < pg_ready_idx < odoo_run_idx

    for kwargs in router.kwargs:
        env = kwargs.get("env")
        if isinstance(env, dict):
            assert env["LANG"] == "C"
            assert env["LC_ALL"] == "C"


def test_pg_readiness_gate_tcp_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME}, pg_ready_after=2
    )
    monkeypatch.setattr(subprocess, "run", router)

    sleeps: list[float] = []
    provider = DockerBackendProvider(sleep=sleeps.append)
    provider.run(_make_plan())

    exec_call = next(c for c in router.calls if c[1] == "exec")
    assert exec_call[2:] == [DB_NAME, "pg_isready", "-h", "127.0.0.1", "-U", "odoo", "-d", "proj"]
    assert len(sleeps) >= 2


def test_pg_readiness_gate_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME}, pg_ready_after=9_999
    )
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, pg_readiness_timeout=3.0, pg_poll_interval=1.0
    )

    with pytest.raises(PostgresReadinessError):
        provider.run(_make_plan())


def test_odoo_health_wait_default_floor() -> None:
    provider = DockerBackendProvider()
    assert provider._health_wait_timeout >= 180.0


def test_odoo_health_wait_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=3.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        provider.run(_make_plan())


def test_run_pulls_exact_digest_image_ref_before_odoo_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(sleep=lambda _seconds: None)
    provider.run(_make_digest_plan())

    pull_call = next(c for c in router.calls if c[1] == "pull")
    odoo_run_idx = next(i for i, c in enumerate(router.calls) if c[1] == "run" and ODOO_NAME in c)

    assert pull_call[-1] == _make_digest_plan().odoo.image
    assert router.calls.index(pull_call) < odoo_run_idx


def test_non_run_paths_do_not_pull_images(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        if argv[1:3] == ["network", "inspect"]:
            return _FakeCompletedProcess(0)
        if argv[1:3] == ["volume", "inspect"]:
            return _FakeCompletedProcess(0)
        if argv[1] == "inspect":
            if len(argv) == 4:
                payload = [
                    _inspect_entry("postgres", running=True, health=None),
                    _inspect_entry("odoo", running=True, health="healthy"),
                ]
                return _FakeCompletedProcess(0, stdout=json.dumps(payload))
            return _FakeCompletedProcess(0, stdout=json.dumps([{"State": {"Running": True}}]))
        if argv[1] == "logs":
            return _FakeCompletedProcess(0, stdout="odoo log lines\n")
        if argv[1] == "exec":
            return _FakeCompletedProcess(0, stdout="exec output", stderr="")
        if argv[1] == "stop" or argv[1] == "rm" or argv[1:3] == ["network", "rm"]:
            return _FakeCompletedProcess(0)
        raise AssertionError(f"unexpected docker invocation: {argv}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider(sleep=lambda _seconds: None)
    ref = _make_ref()

    provider.status(ref)
    provider.stop(ref)
    provider.logs(ref, "odoo")
    provider.exec(ref, ["odoo-bin", "--version"])

    assert not any(call[1] == "pull" for call in calls)


@pytest.mark.parametrize(
    ("stderr", "expected_error"),
    [
        (
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
            DockerUnavailableError,
        ),
        ("manifest unknown", ImageNotFoundError),
        (
            "pull access denied for ghcr.io/odoo/odoo, repository does not exist "
            "or may require 'docker login': denied: requested access "
            "to the resource is denied",
            ImageAuthorizationError,
        ),
    ],
)
def test_run_pull_failures_map_to_typed_backend_errors(
    stderr: str,
    expected_error: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        pull_error_stderr=stderr,
    )
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(sleep=lambda _seconds: None)

    with pytest.raises(expected_error):
        provider.run(_make_plan())

    assert any(call[1] == "pull" for call in router.calls)
    assert not any(call[1] == "run" for call in router.calls)


# -- created-only rollback -------------------------------------------------


def test_partial_failure_rollback_removes_only_created_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        provider.run(_make_plan())

    rm_calls = [c for c in router.calls if c[1] == "rm" and "-f" in c]
    vol_rm_calls = [c for c in router.calls if c[1:3] == ["volume", "rm"]]
    net_rm_calls = [c for c in router.calls if c[1:3] == ["network", "rm"]]

    assert [c[-1] for c in rm_calls] == [ODOO_NAME, DB_NAME]
    assert {c[-1] for c in vol_rm_calls} == {PGDATA_VOL, FILESTORE_VOL}
    assert net_rm_calls[0][-1] == NETWORK

    rm_idx = router.calls.index(rm_calls[0])
    vol_idx = min(router.calls.index(c) for c in vol_rm_calls)
    net_idx = router.calls.index(net_rm_calls[0])
    assert rm_idx < vol_idx < net_idx


def test_rollback_continues_after_one_teardown_step_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """One failing teardown step (odoo `docker rm -f -v` times out) must not

    abort the remaining teardowns (pg container, both volumes, network) AND
    must not mask the original `run()` failure that triggered rollback.
    """
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "rm" and "-f" in argv and ODOO_NAME in argv:
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=1)
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        provider.run(_make_plan())

    rm_calls = [c for c in router.calls if c[1] == "rm" and "-f" in c]
    vol_rm_calls = [c for c in router.calls if c[1:3] == ["volume", "rm"]]
    net_rm_calls = [c for c in router.calls if c[1:3] == ["network", "rm"]]

    # The odoo `rm` call itself raised (recorded only via router when it
    # doesn't raise) — but the pg container's `rm` still ran, and so did
    # both volume removals and the network removal.
    assert [c[-1] for c in rm_calls] == [DB_NAME]
    assert {c[-1] for c in vol_rm_calls} == {PGDATA_VOL, FILESTORE_VOL}
    assert net_rm_calls[0][-1] == NETWORK


def test_readiness_failure_captures_diagnostics_before_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError) as excinfo:
        provider.run(_make_plan())

    assert "readiness diagnostics" in str(excinfo.value)
    log_idx = next(i for i, call in enumerate(router.calls) if call[1] == "logs")
    rollback_idx = next(
        i for i, call in enumerate(router.calls) if call[1] == "rm" and "-f" in call
    )
    assert log_idx < rollback_idx


def test_rollback_failure_is_reported_with_its_residual_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "rm" and "-f" in argv and ODOO_NAME in argv:
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=1)
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(
        ContainerRunError,
        match="cleanup incomplete: container=odoo-forge-proj-default-odoo",
    ):
        provider.run(_make_plan())


def test_reattach_then_fail_preserves_existing_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(
        not_found={NETWORK, DB_NAME, ODOO_NAME},  # volumes already exist (reattach)
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        provider.run(_make_plan())

    vol_rm_calls = [c for c in router.calls if c[1:3] == ["volume", "rm"]]
    assert vol_rm_calls == []

    vol_create_calls = [c for c in router.calls if c[1:3] == ["volume", "create"]]
    assert vol_create_calls == []


def test_run_docker_unavailable_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider()

    with pytest.raises(DockerUnavailableError):
        provider.run(_make_plan())


def test_run_docker_unavailable_daemon_down_stderr_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(
            1, stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider()

    with pytest.raises(DockerUnavailableError):
        provider.run(_make_plan())


def test_run_image_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "run":
            return _FakeCompletedProcess(1, stderr="Unable to find image 'postgres:16' locally")
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider()

    with pytest.raises(ImageNotFoundError):
        provider.run(_make_plan())


def test_run_refuses_existing_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found=set())  # everything already exists
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider()

    with pytest.raises(InstanceExistsError):
        provider.run(_make_plan())

    assert not any(c[1:3] == ["network", "create"] for c in router.calls)


# -- deferred `_health_status` edge cases (tasks 5.5/5.6), via _wait_odoo_healthy --


def test_health_status_no_healthcheck_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Health` absent (no `HEALTHCHECK` on the image) -> `_health_status` None ->
    keeps polling -> times out."""

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout=json.dumps([{"State": {"Running": True}}]))

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        provider._wait_odoo_healthy(_make_plan().odoo)


def test_health_status_empty_inspect_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """`docker inspect` returns `[]` (container removed mid-poll) ->
    `_health_status` None -> times out."""

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout="[]")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider(
        sleep=lambda _seconds: None, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        provider._wait_odoo_healthy(_make_plan().odoo)


# -- status() -----------------------------------------------------------------


def test_status_derives_from_inspect_labels_no_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        assert argv == ["docker", "inspect", DB_NAME, ODOO_NAME]
        payload = [
            _inspect_entry("postgres", running=True, health=None),
            _inspect_entry("odoo", running=True, health="healthy"),
        ]
        return _FakeCompletedProcess(0, stdout=json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", _fake_run)

    status = DockerBackendProvider().status(_make_ref())

    assert status.postgres.running is True
    assert status.postgres.state == "no_healthcheck"
    assert status.odoo.running is True
    assert status.odoo.state == "healthy"
    assert status.odoo.ready is True


def test_status_absent_container_not_running_no_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        # Both role containers externally removed: `docker inspect` exits
        # non-zero but prints an empty JSON array, plus a stderr message —
        # NOT the daemon-down marker.
        return _FakeCompletedProcess(1, stdout="[]", stderr="Error: No such object")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    status = DockerBackendProvider().status(_make_ref())

    assert status.postgres.running is False
    assert status.odoo.running is False


def test_status_daemon_down_raises_docker_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_daemon_down)

    with pytest.raises(DockerUnavailableError):
        DockerBackendProvider().status(_make_ref())


# -- stop() ---------------------------------------------------------------


def test_stop_argv_preserves_named_volumes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        return _FakeCompletedProcess(0)  # both containers/network exist; every op succeeds

    monkeypatch.setattr(subprocess, "run", _fake_run)

    DockerBackendProvider().stop(_make_ref())

    stop_calls = [c for c in calls if c[1] == "stop"]
    rm_calls = [c for c in calls if c[1] == "rm" and "-f" in c]
    vol_rm_calls = [c for c in calls if c[1:3] == ["volume", "rm"]]
    net_rm_calls = [c for c in calls if c[1:3] == ["network", "rm"]]

    assert {c[-1] for c in stop_calls} == {DB_NAME, ODOO_NAME}
    assert {c[-1] for c in rm_calls} == {DB_NAME, ODOO_NAME}
    assert vol_rm_calls == []  # named PG/filestore volumes are never touched
    assert net_rm_calls[0][-1] == NETWORK


def test_stop_partial_instance_stops_only_existing_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Half-torn-down instance: postgres container exists, odoo does not.

    Only the existing container is stopped/removed; the missing one is
    skipped without error; the network is still removed (it doesn't depend
    on either container existing); no `docker volume rm` is ever issued.
    """
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        if argv[1] == "inspect" and len(argv) == 3:
            name = argv[2]
            return _FakeCompletedProcess(0 if name == DB_NAME else 1)
        return _FakeCompletedProcess(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    DockerBackendProvider().stop(_make_ref())

    stop_calls = [c for c in calls if c[1] == "stop"]
    rm_calls = [c for c in calls if c[1] == "rm" and "-f" in c]
    vol_rm_calls = [c for c in calls if c[1:3] == ["volume", "rm"]]
    net_rm_calls = [c for c in calls if c[1:3] == ["network", "rm"]]

    assert {c[-1] for c in stop_calls} == {DB_NAME}
    assert {c[-1] for c in rm_calls} == {DB_NAME}
    assert vol_rm_calls == []
    assert net_rm_calls[0][-1] == NETWORK


def test_stop_unknown_instance_raises_instance_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1)  # neither container exists

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(InstanceNotFoundError):
        DockerBackendProvider().stop(_make_ref())


# -- logs() -----------------------------------------------------------------


def test_logs_returns_str_per_role(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "inspect" and len(argv) == 3:
            return _FakeCompletedProcess(0)
        if argv[1] == "logs":
            assert argv == ["docker", "logs", ODOO_NAME]
            return _FakeCompletedProcess(0, stdout="odoo log lines\n")
        raise AssertionError(f"unexpected invocation: {argv}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    text = DockerBackendProvider().logs(_make_ref(), "odoo")

    assert text == "odoo log lines\n"


def test_logs_absent_instance_raises_instance_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1)  # container does not exist

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(InstanceNotFoundError):
        DockerBackendProvider().logs(_make_ref(), "postgres")


# -- exec() -----------------------------------------------------------------


def test_exec_returns_exit_code_stdout_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "inspect" and len(argv) == 3:
            return _FakeCompletedProcess(0)
        if argv[1] == "exec":
            assert argv == ["docker", "exec", ODOO_NAME, "odoo-bin", "--version"]
            return _FakeCompletedProcess(3, stdout="out", stderr="err")
        raise AssertionError(f"unexpected invocation: {argv}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = DockerBackendProvider().exec(_make_ref(), ["odoo-bin", "--version"])

    assert result.exit_code == 3
    assert result.stdout == "out"
    assert result.stderr == "err"


def test_exec_absent_instance_raises_instance_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1)  # odoo container does not exist

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(InstanceNotFoundError):
        DockerBackendProvider().exec(_make_ref(), ["echo", "hi"])


# -- Protocol conformance (task 10.1/10.2) -----------------------------------


def test_isinstance_backend_provider_conformance() -> None:
    assert isinstance(DockerBackendProvider(), BackendProvider)


def test_signature_conformance_per_method() -> None:
    """`isinstance` only checks method NAMES exist — this pins each method's
    parameter names/order AND every parameter/return annotation against the
    `BackendProvider` Protocol, so a drift like `logs(...) -> str` becoming
    `-> bytes`, or `role: ContainerRole` becoming `role: str`, is caught.

    The port module uses `from __future__ import annotations` (lazy string
    annotations) and only imports its referenced types under
    `TYPE_CHECKING`, so `typing.get_type_hints` cannot resolve them from the
    port module's own globals alone — `port_localns` supplies the concrete
    types so both sides resolve to the same real objects for an
    apples-to-apples comparison.
    """
    port_localns = {
        "BackendPlan": BackendPlan,
        "ContainerRole": ContainerRole,
        "InstanceRef": InstanceRef,
        "InstanceStatus": InstanceStatus,
        "ExecResult": ExecResult,
    }

    for name in ("run", "status", "stop", "logs", "exec"):
        port_method = getattr(BackendProvider, name)
        impl_method = getattr(DockerBackendProvider, name)

        port_sig = inspect.signature(port_method)
        impl_sig = inspect.signature(impl_method)
        port_params = list(port_sig.parameters)
        impl_params = list(impl_sig.parameters)
        assert port_params == impl_params, f"{name}: {port_params} != {impl_params}"

        port_hints = typing.get_type_hints(port_method, localns=port_localns)
        impl_hints = typing.get_type_hints(impl_method)

        for param in port_params:
            if param == "self":
                continue
            assert str(port_hints[param]) == str(impl_hints[param]), (
                f"{name}.{param}: {port_hints[param]!r} != {impl_hints[param]!r}"
            )
        assert str(port_hints["return"]) == str(impl_hints["return"]), (
            f"{name} return: {port_hints['return']!r} != {impl_hints['return']!r}"
        )
