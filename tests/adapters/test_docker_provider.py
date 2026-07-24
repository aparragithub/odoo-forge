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
from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
    OperationIdentity,
    ResourceOwnership,
)
from odoo_forge.ports.backend_provider import BackendProvider
from odoo_forge_docker.credential_injection import SopsCommandResolver, SopsEnvFileInjector
from odoo_forge_docker.provider import (
    _BOOTSTRAP_TIMEOUT_SECONDS,
    DockerBackendProvider,
    _bootstrap_container_argv,
    _docker_env,
    _health_status,
    _network_create_argv,
    _run_container_argv,
    _volume_create_argv,
)

NETWORK = "odoo-forge-proj-default"
DB_NAME = "odoo-forge-proj-default-db"
ODOO_NAME = "odoo-forge-proj-default-odoo"
BOOTSTRAP_NAME = f"{ODOO_NAME}-bootstrap"
PGDATA_VOL = "odoo-forge-proj-default-pgdata"
FILESTORE_VOL = "odoo-forge-proj-default-filestore"


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
        network=network,
        volumes=[pg_volume, fs_volume],
        postgres=postgres,
        odoo=odoo,
        postgres_credentials=CredentialHandle("local-backend/postgres-password"),
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
        self.image_inspect_stderr: str | None = "Error: No such image: odoo-forge-odoo:19.0"
        self.image_inspect_returncode = 1
        self.pg_ready_after: int = 0
        self._pg_attempts = 0
        self.odoo_healthy_after: int = 0
        self._odoo_attempts = 0
        self._created_containers: set[str] = set()
        self._volume_labels: dict[str, dict[str, str]] = {}
        self.bootstrap_exists = False

    def __call__(self, argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        self.calls.append(list(argv))
        self.kwargs.append(kwargs)

        if argv[1:3] == ["network", "inspect"]:
            name = argv[3]
            return _FakeCompletedProcess(1 if name in self.not_found else 0)
        if argv[1:3] == ["volume", "inspect"]:
            name = argv[3]
            if name in self.not_found:
                return _FakeCompletedProcess(1)
            return _FakeCompletedProcess(
                0, stdout=json.dumps([{"Labels": self._volume_labels.get(name, {})}])
            )
        if argv[1:3] == ["image", "inspect"]:
            return _FakeCompletedProcess(
                self.image_inspect_returncode,
                stderr=self.image_inspect_stderr or "",
            )
        if argv[1] == "inspect" and len(argv) == 3:
            name = argv[2]
            if name == BOOTSTRAP_NAME and name not in self._created_containers:
                return _FakeCompletedProcess(0 if self.bootstrap_exists else 1)
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
            name = argv[-1]
            self._volume_labels[name] = {
                value.split("=", 1)[0]: value.split("=", 1)[1]
                for index, value in enumerate(argv)
                if index > 0 and argv[index - 1] == "--label"
            }
            self.not_found.discard(name)
            return _FakeCompletedProcess(0)
        if argv[1] == "pull":
            if self.pull_error_stderr is not None:
                return _FakeCompletedProcess(1, stderr=self.pull_error_stderr)
            return _FakeCompletedProcess(0)
        if argv[1] == "run":
            name = argv[argv.index("--name") + 1]
            self._created_containers.add(name)
            if "--cidfile" in argv:
                Path(argv[argv.index("--cidfile") + 1]).write_text(name)
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


class _FakeDatabaseProvider:
    """Minimal `DatabaseProvider` test double for the backend's delegation seam.

    Never shells out to `docker` itself — the real adapter's own Docker
    argv, topology, and ownership-authority behavior is already covered by
    `tests/adapters/test_postgres_docker_provider.py`. This double only
    needs to prove `DockerBackendProvider`'s delegation seam and two-ledger
    rollback: what spec/credentials it receives, what `DatabaseCreation` it
    returns, and what happens when provisioning or teardown fails.
    """

    def __init__(
        self,
        *,
        data_volume_ownership: ResourceOwnership = ResourceOwnership.CREATED,
        provision_error: Exception | None = None,
        delete_error: Exception | None = None,
        cleanup_residual: bool = False,
    ) -> None:
        self.data_volume_ownership = data_volume_ownership
        self.provision_error = provision_error
        self.delete_error = delete_error
        self.cleanup_residual = cleanup_residual
        self.provision_calls: list[tuple[DatabaseSpec, CredentialHandle]] = []
        self.delete_calls: list[DatabaseCreation] = []
        self.cleanup_calls: list[CreationReceipt] = []
        # Mirrors the real `DockerPostgresqlDatabaseProvider`'s Docker state:
        # `delete()` removes ONLY the container id (`ref.identifier`); a
        # freshly-created data volume also present in `owned_resource_ids`
        # is NEVER touched by `delete()` — only `cleanup()` iterates every
        # owned id. This is the exact shape of the R4 volume-leak the
        # rollback tests below pin against.
        self.removed_resource_ids: set[str] = set()

    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        self.provision_calls.append((spec, credentials))
        if self.provision_error is not None:
            raise self.provision_error
        owned_resource_ids = (spec.name,)
        if spec.data_volume is not None and self.data_volume_ownership is ResourceOwnership.CREATED:
            # Matches the real adapter's `_provision`: a freshly-created data
            # volume is added to the receipt's `owned_resource_ids`; an
            # ADOPTED (pre-existing) volume never is.
            owned_resource_ids = (*owned_resource_ids, spec.data_volume)
        return DatabaseCreation(
            ref=DatabaseRef(identifier=spec.name, ownership=ResourceOwnership.CREATED),
            receipt=CreationReceipt(
                operation=OperationIdentity(value=f"fake-db-{spec.name}"),
                owned_resource_ids=owned_resource_ids,
            ),
            data_volume_ownership=self.data_volume_ownership,
        )

    def restore(self, spec: object, artifact: object, credentials: object) -> DatabaseCreation:
        raise NotImplementedError

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: object) -> DatabaseCreation:
        raise NotImplementedError

    def delete(self, creation: DatabaseCreation) -> None:
        self.delete_calls.append(creation)
        if self.delete_error is not None:
            raise self.delete_error
        self.removed_resource_ids.add(creation.ref.identifier)

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        self.cleanup_calls.append(receipt)
        if self.cleanup_residual:
            return CleanupReport(residual_failures=("db-residual",))
        self.removed_resource_ids.update(receipt.owned_resource_ids)
        return CleanupReport(residual_failures=())


def _run(
    provider: DockerBackendProvider,
    plan: BackendPlan,
    database_provider: _FakeDatabaseProvider | None = None,
) -> InstanceRef:
    """Inject a fake `DatabaseProvider` post-construction, then run.

    Avoids threading `database_provider=` through every one of the many
    `DockerBackendProvider(...)` construction call sites in this file —
    `run()` requires it (design "The delegation seam"), but most tests here
    are not exercising the delegated Postgres leg itself (already covered by
    `tests/adapters/test_postgres_docker_provider.py`), just the backend's
    OWN network/volume/bootstrap/Odoo orchestration around it.
    """
    provider._database_provider = database_provider or _FakeDatabaseProvider()
    return provider.run(plan)


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


def test_bootstrap_argv_reuses_planned_contract_without_ports_or_shell() -> None:
    spec = _make_plan().odoo.model_copy(
        update={
            "name": BOOTSTRAP_NAME,
            "mounts": [
                Mount(
                    root="custom",
                    host_path="/host/addons",
                    container_path="/mnt/addons",
                    read_only=True,
                )
            ],
            "secret_env": {"DB_PASSWORD": CredentialHandle("sops://odoo-db-password")},
        }
    )

    argv = _bootstrap_container_argv(spec, {"DB_PASSWORD": Path("/tmp/db-password")})

    assert argv[:6] == ["docker", "run", "--name", BOOTSTRAP_NAME, "--network", NETWORK]
    assert "-d" not in argv
    assert "-p" not in argv
    assert "sh" not in argv
    assert "DB_HOST=odoo-forge-proj-default-db" in argv
    assert f"{FILESTORE_VOL}:/var/lib/odoo" in argv
    assert "/host/addons:/mnt/addons:ro" in argv
    assert "DB_PASSWORD_FILE=/run/secrets/DB_PASSWORD" in argv
    assert "type=bind,source=/tmp/db-password,target=/run/secrets/DB_PASSWORD,readonly" in argv
    assert argv[-5:] == [
        "odoo-forge-odoo:19.0",
        "-i",
        "base",
        "--stop-after-init",
        "--no-http",
    ]


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
    # Postgres no longer carries `secret_env` here — that leg is delegated
    # (design "Postgres Secret Injection Owned by Adapter"); only the
    # bootstrap (odoo image) and normal Odoo runs still flow through this
    # backend's own `SopsEnvFileInjector.secret_files`.
    secret = "credential-value-not-for-argv"
    plan = _make_plan().model_copy(
        update={
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
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    _run(
        DockerBackendProvider(
            sleep=lambda _seconds: None,
            credential_injector=SopsEnvFileInjector(resolver=lambda _handle: secret),
        ),
        plan,
    )

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
    # `secret_env` remains a valid mechanism on `ContainerSpec` for this
    # unit test of `run()`'s fail-closed credential validation, even though
    # production `plan_backend` no longer populates it for postgres.
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
        _run(DockerBackendProvider(sleep=lambda _seconds: None), plan)

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
        _run(
            DockerBackendProvider(
                sleep=lambda _seconds: None,
                credential_injector=SopsEnvFileInjector(resolver=broken_resolver),
            ),
            plan,
        )

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


def test_run_container_argv_uses_fixed_loopback_port_when_planned() -> None:
    argv = _run_container_argv(
        _make_plan().odoo.model_copy(update={"ports": {"8069": 18069, "8072": None}})
    )

    assert "127.0.0.1:18069:8069" in argv
    assert "127.0.0.1:0:8072" in argv


def test_run_container_argv_uses_planned_bind_host_for_all_odoo_ports() -> None:
    spec = _make_plan().odoo.model_copy(
        update={"bind_host": "192.168.1.20", "ports": {"8069": 18069, "8072": None}}
    )

    argv = _run_container_argv(spec)

    assert "192.168.1.20:18069:8069" in argv
    assert "192.168.1.20:0:8072" in argv
    assert not any("127.0.0.1" in value for value in argv)


def test_run_container_argv_keeps_postgres_unpublished_for_non_loopback_odoo_host() -> None:
    base_plan = _make_plan()
    plan = base_plan.model_copy(
        update={
            "odoo": base_plan.odoo.model_copy(update={"bind_host": "192.168.1.20"}),
        }
    )

    argv = _run_container_argv(plan.postgres)

    assert "-p" not in argv
    assert not any("192.168.1.20" in value for value in argv)


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
    # Postgres provisioning is delegated (design "The delegation seam"), so
    # only network/filestore-volume/Odoo docker calls remain in the
    # backend's own argv sequence — the pgdata volume and the postgres
    # container/readiness argv this test USED to assert on are covered by
    # `tests/adapters/test_postgres_docker_provider.py` instead.
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider()

    provider = DockerBackendProvider(sleep=lambda _seconds: None)
    ref = _run(provider, _make_plan(), fake_db)

    assert ref.postgres_container == DB_NAME
    assert ref.odoo_container == ODOO_NAME
    assert len(fake_db.provision_calls) == 1
    spec, credentials = fake_db.provision_calls[0]
    assert spec.name == DB_NAME
    assert spec.network == NETWORK
    assert spec.data_volume == PGDATA_VOL
    assert credentials == CredentialHandle("local-backend/postgres-password")

    kinds = [tuple(call[:3]) for call in router.calls]
    assert ("docker", "pull", _make_plan().odoo.image) in kinds
    assert ("docker", "inspect", ODOO_NAME) in kinds
    assert not any(call[1] == "run" and DB_NAME in call for call in router.calls)
    assert router.calls[kinds.index(("docker", "network", "create"))][:3] == [
        "docker",
        "network",
        "create",
    ]

    pull_idx = next(i for i, c in enumerate(router.calls) if c[1] == "pull")
    network_idx = next(i for i, c in enumerate(router.calls) if c[1:3] == ["network", "create"])
    filestore_idx = next(
        i
        for i, c in enumerate(router.calls)
        if c[1:3] == ["volume", "create"] and c[-1] == FILESTORE_VOL
    )
    odoo_run_idx = next(i for i, c in enumerate(router.calls) if c[1] == "run" and ODOO_NAME in c)

    assert pull_idx < network_idx < filestore_idx < odoo_run_idx

    for kwargs in router.kwargs:
        env = kwargs.get("env")
        if isinstance(env, dict):
            assert env["LANG"] == "C"
            assert env["LC_ALL"] == "C"


def test_run_uses_exact_local_odoo_image_without_pulling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        image_inspect_returncode=0,
        image_inspect_stderr=None,
    )
    monkeypatch.setattr(subprocess, "run", router)

    _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert ["docker", "image", "inspect", _make_plan().odoo.image] in router.calls
    assert not any(call[1] == "pull" for call in router.calls)


def test_run_pulls_exact_odoo_image_only_when_local_inspection_reports_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    inspect_idx = router.calls.index(["docker", "image", "inspect", _make_plan().odoo.image])
    pull_idx = next(i for i, call in enumerate(router.calls) if call[1] == "pull")
    assert inspect_idx < pull_idx
    assert router.calls[pull_idx] == ["docker", "pull", _make_plan().odoo.image]


def test_run_fails_closed_on_unexpected_local_image_inspection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        image_inspect_stderr="permission denied while inspecting image",
    )
    monkeypatch.setattr(subprocess, "run", router)

    with pytest.raises(ContainerRunError, match="permission denied"):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert not any(call[1] == "pull" for call in router.calls)
    assert not any(call[1:3] == ["network", "create"] for call in router.calls)


def test_run_classifies_local_image_daemon_failure_without_pulling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        image_inspect_stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
    )
    monkeypatch.setattr(subprocess, "run", router)

    with pytest.raises(DockerUnavailableError):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert not any(call[1] == "pull" for call in router.calls)


def test_preexisting_volume_is_not_created_or_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router()
    monkeypatch.setattr(subprocess, "run", router)
    created: list[tuple[str, str] | tuple[str, str, str]] = []

    owned = DockerBackendProvider()._ensure_volume(_make_plan().volumes[0], created)

    assert owned is False
    assert created == []
    assert not any(call[1:3] == ["volume", "create"] for call in router.calls)


def test_concurrent_foreign_volume_is_not_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found={PGDATA_VOL})
    original = router.__call__

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        result = original(argv, **kwargs)
        if argv[1:3] == ["volume", "create"]:
            router._volume_labels[PGDATA_VOL] = {"foreign": "owner"}
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    created: list[tuple[str, str] | tuple[str, str, str]] = []

    with pytest.raises(ContainerRunError, match="volume ownership verification failed"):
        DockerBackendProvider()._ensure_volume(_make_plan().volumes[0], created)

    assert created[0][:2] == ("volume", PGDATA_VOL)


def test_created_volume_is_owned_only_when_unique_label_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={PGDATA_VOL})
    monkeypatch.setattr(subprocess, "run", router)
    created: list[tuple[str, str] | tuple[str, str, str]] = []

    owned = DockerBackendProvider()._ensure_volume(_make_plan().volumes[0], created)

    assert owned is True
    assert created[0][:2] == ("volume", PGDATA_VOL)
    assert router._volume_labels[PGDATA_VOL]["com.odoo-forge.create-token"]


def test_malformed_post_create_inspect_reports_owned_volume_cleanup_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Retargeted from the pgdata volume to the filestore volume: pgdata's
    # `_ensure_volume` call moved to the delegated `DatabaseProvider`
    # (design "The delegation seam"), but the backend still owns and
    # `_ensure_volume`s the filestore volume directly, so this
    # malformed-post-create-inspect regression guard stays meaningful there.
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1:3] == ["volume", "inspect"] and FILESTORE_VOL in router._volume_labels:
            return _FakeCompletedProcess(0, stdout="not-json")
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ContainerRunError) as excinfo:
        _run(DockerBackendProvider(), _make_plan())

    assert f"cleanup incomplete: volume={FILESTORE_VOL}" in str(excinfo.value)
    assert ["docker", "volume", "rm", FILESTORE_VOL] not in router.calls


def test_run_bootstraps_only_when_delegated_provision_reports_created_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    _run(
        DockerBackendProvider(sleep=lambda _seconds: None),
        _make_plan(),
        _FakeDatabaseProvider(data_volume_ownership=ResourceOwnership.CREATED),
    )

    bootstrap_run = next(
        call
        for call in router.calls
        if call[1] == "run" and call[call.index("--name") + 1] == BOOTSTRAP_NAME
    )
    normal_run = next(
        call
        for call in router.calls
        if call[1] == "run" and call[call.index("--name") + 1] == ODOO_NAME
    )
    bootstrap_rm = ["docker", "rm", "-f", "-v", BOOTSTRAP_NAME]
    assert bootstrap_run[-4:] == ["-i", "base", "--stop-after-init", "--no-http"]
    assert router.kwargs[router.calls.index(bootstrap_run)]["timeout"] == 300.0
    assert _BOOTSTRAP_TIMEOUT_SECONDS == 300.0
    assert router.calls.index(bootstrap_run) < router.calls.index(bootstrap_rm)
    assert router.calls.index(bootstrap_rm) < router.calls.index(normal_run)


def test_run_skips_bootstrap_when_delegated_provision_reports_adopted_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    _run(
        DockerBackendProvider(sleep=lambda _seconds: None),
        _make_plan(),
        _FakeDatabaseProvider(data_volume_ownership=ResourceOwnership.ADOPTED),
    )

    assert not any(call[1] == "run" and BOOTSTRAP_NAME in call for call in router.calls)


def test_run_refuses_bootstrap_name_collision_before_provisioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    router.bootstrap_exists = True
    monkeypatch.setattr(subprocess, "run", router)

    with pytest.raises(InstanceExistsError, match=BOOTSTRAP_NAME):
        _run(DockerBackendProvider(), _make_plan())

    assert not any(call[1:3] == ["network", "create"] for call in router.calls)


def test_foreign_volume_has_no_deletion_or_bootstrap_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Retargeted from the pgdata volume to the filestore volume: this
    # `_ensure_volume` race-detection defense is a property of the
    # BACKEND's own ownership-token scheme, which pgdata no longer goes
    # through (design "The delegation seam"; the adapter's own
    # `_ensure_data_volume` has a different, documented TOCTOU posture —
    # design Non-Goals). The filestore volume still exercises the same
    # backend-owned code path this test protects.
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    original = router.__call__

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        result = original(argv, **kwargs)
        if argv[1:3] == ["volume", "create"] and argv[-1] == FILESTORE_VOL:
            router._volume_labels[FILESTORE_VOL] = {"foreign": "owner"}
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    clock = _FakeClock()

    with pytest.raises(ContainerRunError, match="volume ownership verification failed"):
        _run(DockerBackendProvider(monotonic=clock, sleep=clock.advance), _make_plan())

    assert ["docker", "volume", "rm", FILESTORE_VOL] not in router.calls
    assert ["docker", "network", "rm", NETWORK] in router.calls
    assert not any(call[1] in {"run", "exec"} for call in router.calls)


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired([], 300.0), OSError("lost pipe")])
def test_bootstrap_exception_removes_only_cidfile_container(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "run" and argv[argv.index("--name") + 1] == BOOTSTRAP_NAME:
            router.calls.append(list(argv))
            Path(argv[argv.index("--cidfile") + 1]).write_text("owned-bootstrap-id")
            raise failure
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ContainerRunError, match="bootstrap failed"):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert ["docker", "rm", "-f", "-v", "owned-bootstrap-id"] in router.calls
    assert ["docker", "rm", "-f", "-v", BOOTSTRAP_NAME] not in router.calls


def test_bootstrap_failure_redacts_bounded_output_and_prevents_normal_odoo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "bootstrap-secret"
    output = "x" * 10 + secret + "z" * 7_995
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "run" and argv[argv.index("--name") + 1] == BOOTSTRAP_NAME:
            router.calls.append(list(argv))
            Path(argv[argv.index("--cidfile") + 1]).write_text(BOOTSTRAP_NAME)
            return _FakeCompletedProcess(1, stdout=output)
        if argv == ["docker", "logs", "--tail", "200", BOOTSTRAP_NAME]:
            router.calls.append(list(argv))
            return _FakeCompletedProcess(0, stdout=secret)
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = DockerBackendProvider(
        sleep=lambda _seconds: None,
        credential_injector=SopsEnvFileInjector(resolver=lambda _handle: secret),
    )
    plan = _make_plan().model_copy(
        update={
            "odoo": _make_plan().odoo.model_copy(
                update={"secret_env": {"DB_PASSWORD": CredentialHandle("sops://odoo")}}
            )
        }
    )
    fake_db = _FakeDatabaseProvider()

    with pytest.raises(ContainerRunError) as excinfo:
        _run(provider, plan, fake_db)

    message = str(excinfo.value)
    assert output[-8_000:].startswith(secret[-5:]) and secret[-5:] not in message
    assert secret not in message
    assert len(message) < 9_000
    assert ["docker", "rm", "-f", "-v", BOOTSTRAP_NAME] in router.calls
    assert not any(call[1] == "run" and ODOO_NAME in call for call in router.calls)
    # The postgres leg's teardown is delegated (two-ledger rollback, design
    # "Rollback Coordination") — the backend never issues `docker volume rm`
    # for pgdata itself, it calls `db_provider.cleanup(receipt)` (R4 fix:
    # `delete()` alone would leak a freshly-created data volume).
    assert len(fake_db.cleanup_calls) == 1
    assert fake_db.delete_calls == []


def test_bootstrap_name_race_skips_foreign_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "run" and argv[argv.index("--name") + 1] == BOOTSTRAP_NAME:
            raise OSError("safe process failure")
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ContainerRunError, match="safe process failure"):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert router.calls.count(["docker", "inspect", BOOTSTRAP_NAME]) == 1
    assert ["docker", "logs", "--tail", "200", BOOTSTRAP_NAME] not in router.calls


def test_bootstrap_removal_failure_prevents_normal_odoo_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv == ["docker", "rm", "-f", "-v", BOOTSTRAP_NAME]:
            router.calls.append(list(argv))
            return _FakeCompletedProcess(1, stderr="bootstrap removal failed")
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ContainerRunError, match="bootstrap removal failed"):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert not any(call[1] == "run" and ODOO_NAME in call for call in router.calls)
    assert router.calls.count(["docker", "rm", "-f", "-v", BOOTSTRAP_NAME]) == 2


# -- Postgres readiness gating moved to the delegated `DatabaseProvider` --
#
# `_wait_pg_ready` was removed from `DockerBackendProvider` (design "The
# delegation seam"); the equivalent readiness-probe coverage now lives in
# `tests/adapters/test_postgres_docker_provider.py`'s `_wait_ready` tests.
# This REPLACES the retired `test_pg_readiness_gate_tcp_scoped` and
# `test_pg_readiness_gate_times_out`.


def test_run_never_calls_pg_isready_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    assert not any(call[1] == "exec" and "pg_isready" in call for call in router.calls)


def test_odoo_health_wait_default_is_300_seconds_and_override_is_retained() -> None:
    assert DockerBackendProvider()._health_wait_timeout == 300.0
    assert DockerBackendProvider(health_wait_timeout=3.0)._health_wait_timeout == 3.0


@pytest.mark.parametrize(
    ("returncode", "first_inspect"),
    [
        (0, json.dumps([{"State": {"Health": {"Status": "unhealthy"}}}])),
        (1, ""),
        (0, json.dumps([{"State": {"Health": {"Status": "unknown"}}}])),
        (0, json.dumps([{"State": {"Health": {"Status": "starting"}}}])),
    ],
)
def test_odoo_health_wait_recovers_from_transient_state_before_deadline(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    first_inspect: str,
) -> None:
    clock = _FakeClock()
    inspections = iter(
        [
            _FakeCompletedProcess(returncode, stdout=first_inspect),
            _FakeCompletedProcess(0, stdout=_healthy_inspect(ODOO_NAME)),
        ]
    )

    def fake_run(argv: list[str], **_kwargs: object) -> _FakeCompletedProcess:
        assert argv == ["docker", "inspect", ODOO_NAME]
        return next(inspections)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = DockerBackendProvider(
        health_wait_timeout=2.0,
        health_poll_interval=1.0,
        monotonic=clock,
        sleep=clock.advance,
    )

    provider._wait_odoo_healthy(_make_plan().odoo)

    assert clock.now == 1.0


def test_odoo_health_wait_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)

    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=3.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan())


# -- Odoo-only readiness gating (postgres gate retired) --
#
# These were previously parametrized over `("postgres", "odoo")` gates,
# exercising `_wait_pg_ready` (now removed — design "The delegation seam")
# alongside `_wait_odoo_healthy`. The postgres-gate coverage moved to
# `tests/adapters/test_postgres_docker_provider.py`'s `_wait_ready` tests;
# these REPLACE the retired parametrizations with Odoo-only variants.


@pytest.mark.parametrize(
    ("budget", "poll_interval", "expected_timeouts", "expected_sleeps"),
    [
        (2.5, 1.0, [2.5, 0.6], [1.0]),
        (1.2, 1.0, [1.2], [0.3]),
        (0.1, 1.0, [0.1], []),
    ],
)
def test_readiness_deadline_caps_probes_and_charges_invocations_and_sleeps(
    monkeypatch: pytest.MonkeyPatch,
    budget: float,
    poll_interval: float,
    expected_timeouts: list[float],
    expected_sleeps: list[float],
) -> None:
    clock = _FakeClock()
    timeouts: list[float] = []
    sleeps: list[float] = []

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, float)
        timeouts.append(timeout)
        clock.advance(min(0.9, timeout))
        return _FakeCompletedProcess(
            0, stdout=json.dumps([{"State": {"Health": {"Status": "starting"}}}])
        )

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = DockerBackendProvider(
        docker_timeout=30.0,
        health_wait_timeout=budget,
        health_poll_interval=poll_interval,
        monotonic=clock,
        sleep=fake_sleep,
    )

    with pytest.raises(ContainerRunError):
        provider._wait_odoo_healthy(_make_plan().odoo)

    assert timeouts == pytest.approx(expected_timeouts)
    assert sleeps == pytest.approx(expected_sleeps)
    assert clock.now <= budget + 0.9


def test_exhausted_readiness_deadline_does_not_start_zero_timeout_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        nonlocal calls
        calls += 1
        timeout = kwargs["timeout"]
        assert isinstance(timeout, float)
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = DockerBackendProvider(health_wait_timeout=0.0, monotonic=lambda: 10.0)

    with pytest.raises(ContainerRunError):
        provider._wait_odoo_healthy(_make_plan().odoo)

    assert calls == 0


def test_readiness_probe_timeout_before_deadline_remains_docker_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, float) and timeout > 0.0
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = DockerBackendProvider(health_wait_timeout=1.0, monotonic=lambda: 10.0)

    with pytest.raises(DockerUnavailableError):
        provider._wait_odoo_healthy(_make_plan().odoo)


def test_readiness_accepts_success_from_final_budgeted_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    timeouts: list[float] = []

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, float)
        timeouts.append(timeout)
        clock.advance(min(0.5, timeout))
        if len(timeouts) == 2:
            return _FakeCompletedProcess(0, stdout=_healthy_inspect(ODOO_NAME))
        return _FakeCompletedProcess(2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = DockerBackendProvider(
        health_wait_timeout=1.25,
        health_poll_interval=0.5,
        monotonic=clock,
        sleep=clock.advance,
    )

    provider._wait_odoo_healthy(_make_plan().odoo)

    assert timeouts == pytest.approx([1.25, 0.25])


def test_run_pulls_exact_digest_image_ref_before_odoo_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider(sleep=lambda _seconds: None)
    _run(provider, _make_digest_plan())

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
        _run(provider, _make_plan())

    assert any(call[1] == "pull" for call in router.calls)
    assert not any(call[1] == "run" for call in router.calls)


def test_run_maps_generic_pull_failure_after_local_image_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        pull_error_stderr="unexpected pull failure: checksum mismatch",
    )
    monkeypatch.setattr(subprocess, "run", router)

    with pytest.raises(ContainerRunError, match="unexpected pull failure: checksum mismatch"):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan())

    inspect_idx = router.calls.index(["docker", "image", "inspect", _make_plan().odoo.image])
    pull_idx = next(i for i, call in enumerate(router.calls) if call[1] == "pull")
    assert inspect_idx < pull_idx
    assert not any(call[1] == "run" for call in router.calls)


# -- created-only rollback -------------------------------------------------


def test_partial_failure_rollback_removes_only_created_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two-ledger rollback (design "Rollback Coordination"): the postgres leg
    # is torn down via `db_provider.cleanup(receipt)` (R4 fix), never via
    # `docker rm -f`/`docker volume rm` issued by the backend itself — only
    # the Odoo container and the filestore volume go through the router.
    router = _make_router(
        not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider()

    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan(), fake_db)

    rm_calls = [c for c in router.calls if c[1] == "rm" and "-f" in c]
    vol_rm_calls = [c for c in router.calls if c[1:3] == ["volume", "rm"]]
    net_rm_calls = [c for c in router.calls if c[1:3] == ["network", "rm"]]

    assert [c[-1] for c in rm_calls] == [BOOTSTRAP_NAME, ODOO_NAME]
    assert {c[-1] for c in vol_rm_calls} == {FILESTORE_VOL}
    assert net_rm_calls[0][-1] == NETWORK
    assert len(fake_db.cleanup_calls) == 1
    assert fake_db.delete_calls == []
    # R4 fix: the freshly-created pgdata volume (data_volume_ownership ==
    # CREATED by default) must be fully reclaimed via `cleanup()`, not just
    # the container — this is the exact resource the pre-fix `delete()`-only
    # rollback path silently leaked.
    assert PGDATA_VOL in fake_db.removed_resource_ids
    assert DB_NAME in fake_db.removed_resource_ids

    odoo_rm_idx = next(
        i for i, c in enumerate(router.calls) if c == ["docker", "rm", "-f", "-v", ODOO_NAME]
    )
    vol_idx = min(router.calls.index(c) for c in vol_rm_calls)
    net_idx = router.calls.index(net_rm_calls[0])
    assert odoo_rm_idx < vol_idx < net_idx


def test_rollback_continues_after_one_teardown_step_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """One failing teardown step (odoo `docker rm -f -v` times out) must not

    abort the remaining teardowns (the delegated postgres leg, the filestore
    volume, the network) AND must not mask the original `run()` failure
    that triggered rollback.
    """
    router = _make_router(
        not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "rm" and "-f" in argv and ODOO_NAME in argv:
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=1)
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    fake_db = _FakeDatabaseProvider()

    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan(), fake_db)

    rm_calls = [c for c in router.calls if c[1] == "rm" and "-f" in c]
    vol_rm_calls = [c for c in router.calls if c[1:3] == ["volume", "rm"]]
    net_rm_calls = [c for c in router.calls if c[1:3] == ["network", "rm"]]

    # The odoo `rm` call itself raised (recorded only via router when it
    # doesn't raise) — but the delegated postgres leg's `cleanup()` still
    # ran (R4 fix), and so did the filestore volume removal and the network
    # removal.
    assert [c[-1] for c in rm_calls] == [BOOTSTRAP_NAME]
    assert {c[-1] for c in vol_rm_calls} == {FILESTORE_VOL}
    assert net_rm_calls[0][-1] == NETWORK
    assert len(fake_db.cleanup_calls) == 1
    assert fake_db.delete_calls == []


def test_readiness_timeout_reports_selected_inspect_and_bounded_combined_logs_before_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    inspect_payload = json.dumps(
        [
            {
                "Config": {"Env": ["DO_NOT_REPORT"]},
                "Mounts": [{"Source": "DO_NOT_REPORT"}],
                "State": {
                    "Status": "running",
                    "Running": True,
                    "ExitCode": 0,
                    "Error": "y" * 9_000 + "state error",
                    "OOMKilled": False,
                    "Health": {"Status": "unhealthy", "FailingStreak": 2},
                },
            }
        ]
    )

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv == ["docker", "inspect", ODOO_NAME] and ODOO_NAME in router._created_containers:
            router.calls.append(list(argv))
            return _FakeCompletedProcess(0, stdout=inspect_payload)
        if argv == ["docker", "logs", "--tail", "200", ODOO_NAME]:
            router.calls.append(list(argv))
            return _FakeCompletedProcess(
                0, stdout="x" * 9_000 + "stdout excerpt", stderr="stderr excerpt"
            )
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError) as excinfo:
        _run(provider, _make_plan())

    message = str(excinfo.value)
    assert "odoo readiness timed out after 1s" in message
    assert "final_health=unhealthy" in message
    assert '"FailingStreak": 2' in message
    assert "stdout excerpt" in message
    assert "stderr excerpt" in message
    assert "x" * 8_001 not in message
    assert "y" * 8_001 not in message and "state error" in message
    assert "DO_NOT_REPORT" not in message
    log_idx = router.calls.index(["docker", "logs", "--tail", "200", ODOO_NAME])
    rollback_idx = next(
        i
        for i, call in enumerate(router.calls)
        if call[1] == "rm" and "-f" in call and call[-1] == ODOO_NAME
    )
    assert log_idx < rollback_idx


@pytest.mark.parametrize("capture_failure", ["malformed", "nonzero", "exception"])
def test_readiness_timeout_uses_unavailable_markers_when_capture_fails(
    monkeypatch: pytest.MonkeyPatch, capture_failure: str
) -> None:
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        is_created = ODOO_NAME in router._created_containers
        if argv == ["docker", "inspect", ODOO_NAME] and is_created:
            if capture_failure == "exception" and kwargs["timeout"] == 30.0:
                raise OSError("inspect unavailable")
            return _FakeCompletedProcess(0, stdout="not-json")
        if argv == ["docker", "logs", "--tail", "200", ODOO_NAME]:
            if capture_failure == "exception":
                raise OSError("logs unavailable")
            return _FakeCompletedProcess(1, stderr="logs unavailable")
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError) as excinfo:
        _run(provider, _make_plan())

    message = str(excinfo.value)
    assert "final_health=unknown" in message
    assert "inspect=unavailable" in message
    assert "logs=unavailable" in message


def test_readiness_timeout_redacts_resolved_and_planned_environment_values_longest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_secret = "database-value"
    shorter_value = resolved_secret
    longer_value = f"{shorter_value}-suffix"
    plan = _make_plan().model_copy(
        update={
            "postgres": _make_plan().postgres.model_copy(
                update={
                    "env": {
                        "POSTGRES_PASSWORD": shorter_value,
                        "POSTGRES_USER": longer_value,
                        "POSTGRES_DB": "planned-database",
                    },
                    "secret_env": {"POSTGRES_PASSWORD": CredentialHandle("sops://postgres")},
                }
            ),
            "odoo": _make_plan().odoo.model_copy(
                update={
                    "env": {
                        "DB_HOST": "planned-host",
                        "DB_PORT": "planned-port",
                        "DB_USER": "planned-user",
                        "DB_PASSWORD": "planned-password",
                    }
                }
            ),
        }
    )
    router = _make_router(
        not_found={NETWORK, PGDATA_VOL, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    raw_diagnostics = " ".join(
        [resolved_secret, shorter_value, longer_value, *plan.odoo.env.values()]
    )

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv == ["docker", "inspect", ODOO_NAME] and ODOO_NAME in router._created_containers:
            return _FakeCompletedProcess(
                0,
                stdout=json.dumps(
                    [{"State": {"Error": raw_diagnostics, "Health": {"Status": "starting"}}}]
                ),
            )
        if argv == ["docker", "logs", "--tail", "200", ODOO_NAME]:
            return _FakeCompletedProcess(0, stdout=raw_diagnostics, stderr=raw_diagnostics)
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
        credential_injector=SopsEnvFileInjector(resolver=lambda _handle: resolved_secret),
    )

    with pytest.raises(ContainerRunError) as excinfo:
        _run(provider, plan)

    message = str(excinfo.value)
    assert "[REDACTED]-suffix" not in message
    assert message.count("[REDACTED]") >= 3
    assert resolved_secret not in message
    assert shorter_value not in message
    assert longer_value not in message
    assert all(value not in message for value in plan.odoo.env.values() if value)


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
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError) as excinfo:
        _run(provider, _make_plan())

    message = str(excinfo.value)
    assert "odoo readiness timed out after 1s" in message
    assert "final_health=" in message
    assert f"cleanup incomplete: container={ODOO_NAME}" in message


def test_reattach_then_fail_preserves_existing_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(
        not_found={NETWORK, DB_NAME, ODOO_NAME},  # volumes already exist (reattach)
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)

    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock,
        sleep=clock.advance,
        health_wait_timeout=1.0,
        health_poll_interval=1.0,
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan())

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
        _run(provider, _make_plan())


def test_run_docker_unavailable_daemon_down_stderr_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(
            1, stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider()

    with pytest.raises(DockerUnavailableError):
        _run(provider, _make_plan())


def test_run_image_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the Odoo image-not-found path remains reachable through the
    # backend's own `_run_container`/`_exec` (which classifies this stderr
    # marker); the postgres leg is delegated (design "The delegation
    # seam"), so `data_volume_ownership=ADOPTED` skips the bootstrap run
    # and isolates the failure to the normal Odoo `docker run`.
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if argv[1] == "run" and ODOO_NAME in argv:
            return _FakeCompletedProcess(1, stderr="Unable to find image 'odoo-forge-odoo' locally")
        return router(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = DockerBackendProvider()

    with pytest.raises(ImageNotFoundError):
        _run(
            provider,
            _make_plan(),
            _FakeDatabaseProvider(data_volume_ownership=ResourceOwnership.ADOPTED),
        )


def test_run_refuses_existing_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    router = _make_router(not_found=set())  # everything already exists
    monkeypatch.setattr(subprocess, "run", router)

    provider = DockerBackendProvider()

    with pytest.raises(InstanceExistsError):
        _run(provider, _make_plan())

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
        assert kwargs["capture_output"] is True
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


# -- Phase 6/7: backend delegation seam + two-ledger rollback --
#
# REPLACES the retired Phase 0 characterization tests
# (`test_run_postgres_leg_calls_ensure_volume_then_run_container_then_wait_pg_ready`,
# `test_run_bootstrap_gate_is_the_raw_ensure_volume_return_value`,
# `test_run_rollback_order_on_odoo_start_failure_is_containers_then_volumes_then_network`)
# that pinned the pre-cutover inline Postgres leg and single-ledger
# rollback order — those tests explicitly documented that Phase 6/7 would
# replace them, so this replacement is the deliberate, visible change they
# were designed to require, not a silent regression.


def test_run_requires_an_injected_database_provider() -> None:
    with pytest.raises(ContainerRunError, match="DatabaseProvider"):
        DockerBackendProvider().run(_make_plan())


def test_run_requires_postgres_credentials_on_the_plan() -> None:
    plan = _make_plan().model_copy(update={"postgres_credentials": None})
    provider = DockerBackendProvider()
    provider._database_provider = _FakeDatabaseProvider()

    with pytest.raises(ContainerRunError, match="postgres_credentials"):
        provider.run(plan)


def test_run_delegates_postgres_exclusively_to_the_injected_database_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider()

    _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan(), fake_db)

    assert len(fake_db.provision_calls) == 1
    spec, credentials = fake_db.provision_calls[0]
    assert spec.name == DB_NAME
    assert spec.network == NETWORK
    assert spec.data_volume == PGDATA_VOL
    assert spec.env["POSTGRES_USER"] == "odoo"
    assert spec.env["POSTGRES_DB"] == "proj"
    assert credentials == CredentialHandle("local-backend/postgres-password")
    assert not any(call[1] == "run" and DB_NAME in call for call in router.calls)
    assert not any(call[1] == "exec" and "pg_isready" in call for call in router.calls)


@pytest.mark.parametrize(
    ("ownership", "expect_bootstrap"),
    [(ResourceOwnership.CREATED, True), (ResourceOwnership.ADOPTED, False)],
)
def test_run_bootstrap_gate_is_data_volume_ownership_not_container_ownership(
    monkeypatch: pytest.MonkeyPatch,
    ownership: ResourceOwnership,
    expect_bootstrap: bool,
) -> None:
    """Gates the bootstrap-seed on `creation.data_volume_ownership`, never on

    `creation.ref.ownership` (which is always `CREATED` for the container —
    design "Fresh-pgdata Signal Gates Odoo Bootstrap-Seed", spec r2).
    """
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)

    _run(
        DockerBackendProvider(sleep=lambda _seconds: None),
        _make_plan(),
        _FakeDatabaseProvider(data_volume_ownership=ownership),
    )

    ran_bootstrap = any(
        call[1] == "run" and call[call.index("--name") + 1] == BOOTSTRAP_NAME
        for call in router.calls
    )
    assert ran_bootstrap is expect_bootstrap


def test_run_rollback_order_on_odoo_start_failure_is_odoo_then_database_then_filestore_then_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two-ledger rollback order when Odoo never becomes healthy (design

    "Rollback Coordination (two ledgers)"): Odoo container first (reverse-
    created order), then the delegated postgres leg via `db_provider`, then
    the filestore volume, then the network last.
    """
    router = _make_router(
        not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider()
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock, sleep=clock.advance, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan(), fake_db)

    rm_calls = [call for call in router.calls if call[1] == "rm" and "-f" in call]
    vol_rm_calls = [call for call in router.calls if call[1:3] == ["volume", "rm"]]
    net_rm_calls = [call for call in router.calls if call[1:3] == ["network", "rm"]]

    assert [call[-1] for call in rm_calls] == [BOOTSTRAP_NAME, ODOO_NAME]
    assert len(fake_db.cleanup_calls) == 1
    assert fake_db.delete_calls == []
    last_container_rm_idx = router.calls.index(rm_calls[-1])
    first_volume_rm_idx = min(router.calls.index(call) for call in vol_rm_calls)
    network_rm_idx = router.calls.index(net_rm_calls[0])
    assert last_container_rm_idx < first_volume_rm_idx < network_rm_idx


def test_run_provision_failure_never_touches_postgres_leg_via_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Postgres provisioning failure, the adapter has already

    self-cleaned its own leg via its receipt — the backend rolls back only
    what it already created (the network) and never calls `delete()`/
    `cleanup()` on a `DatabaseCreation` that was never returned (design
    "on Postgres provisioning failure the adapter self-cleans").
    """
    router = _make_router(not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME})
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider(provision_error=ContainerRunError("adapter self-cleaned"))

    with pytest.raises(ContainerRunError, match="adapter self-cleaned"):
        _run(DockerBackendProvider(sleep=lambda _seconds: None), _make_plan(), fake_db)

    assert fake_db.delete_calls == []
    assert fake_db.cleanup_calls == []
    assert ["docker", "network", "rm", NETWORK] in router.calls
    assert ["docker", "volume", "rm", FILESTORE_VOL] in router.calls


def test_run_rollback_on_backend_triggered_failure_removes_freshly_created_pgdata_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R4 fix (CRITICAL volume-leak regression): a backend-triggered rollback

    (here, Odoo never becoming healthy) after a successful Postgres
    provision whose `data_volume_ownership == CREATED` MUST fully remove the
    freshly-created pgdata volume, not just the container. Pre-fix,
    `_rollback_database` called `delete(creation)` first — which the real
    adapter's `delete()` implements as removing ONLY
    `creation.ref.identifier` (the container) — and `delete()` succeeded
    without raising, so `_rollback_database` returned `True` and never
    reached `cleanup(receipt)`, silently leaking the volume. This test is
    RED against that code (asserts `cleanup()` is the rollback path and the
    volume ends up removed) and GREEN once `_rollback_database` calls
    `cleanup(receipt)` unconditionally.
    """
    router = _make_router(
        not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider(data_volume_ownership=ResourceOwnership.CREATED)
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock, sleep=clock.advance, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan(), fake_db)

    assert fake_db.delete_calls == []
    assert len(fake_db.cleanup_calls) == 1
    assert fake_db.cleanup_calls[0].owned_resource_ids == (DB_NAME, PGDATA_VOL)
    assert PGDATA_VOL in fake_db.removed_resource_ids
    assert DB_NAME in fake_db.removed_resource_ids


def test_run_rollback_on_backend_triggered_failure_preserves_adopted_pgdata_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Symmetric guard: an ADOPTED (pre-existing) data volume is never added

    to `owned_resource_ids` by the adapter, so `cleanup(receipt)` — the
    rollback path after the R4 fix — must never remove it either.
    """
    router = _make_router(
        not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider(data_volume_ownership=ResourceOwnership.ADOPTED)
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock, sleep=clock.advance, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError):
        _run(provider, _make_plan(), fake_db)

    assert fake_db.delete_calls == []
    assert len(fake_db.cleanup_calls) == 1
    assert fake_db.cleanup_calls[0].owned_resource_ids == (DB_NAME,)
    assert PGDATA_VOL not in fake_db.removed_resource_ids
    assert DB_NAME in fake_db.removed_resource_ids


def test_run_rollback_reports_residual_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _make_router(
        not_found={NETWORK, FILESTORE_VOL, DB_NAME, ODOO_NAME},
        odoo_healthy_after=9_999,
    )
    monkeypatch.setattr(subprocess, "run", router)
    fake_db = _FakeDatabaseProvider(cleanup_residual=True)
    clock = _FakeClock()
    provider = DockerBackendProvider(
        monotonic=clock, sleep=clock.advance, health_wait_timeout=1.0, health_poll_interval=1.0
    )

    with pytest.raises(ContainerRunError) as excinfo:
        _run(provider, _make_plan(), fake_db)

    assert f"cleanup incomplete: database={DB_NAME}" in str(excinfo.value)
