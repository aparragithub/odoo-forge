"""Disposable pinned-host SSH/Docker evidence for the first VPS adapter."""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.request import urlopen

import pytest

from odoo_forge.backend.plan import (
    BackendPlan,
    ContainerSpec,
    NetworkSpec,
    VolumeSpec,
    plan_backend,
)
from odoo_forge.backend.status import InstanceRef
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.deployment_spec.types import (
    DeploymentSpec,
    ExposureIntent,
    OdooRuntimeIntent,
    RequirementPolicy,
    RouteProtocol,
)
from odoo_forge.durable_operations.types import DurableOperationIdentity, LifecycleState
from odoo_forge.exposure.types import ExposureRequest, ExposureResult
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.manifest.projection import MountPlanningView
from odoo_forge.manifest.schema import BackendConfig, Client, Manifest, OdooBackendConfig
from odoo_forge.resource_ownership.types import (
    OwnershipReceipt,
    OwnershipRecord,
    ResourceOwnership,
    ResourceRef,
)
from odoo_forge.tenancy.types import ProjectScope, TenantId
from odoo_forge_docker.vps.provider import (
    RemoteDockerMechanics,
    VpsOperationBinding,
    VpsTargetIdentity,
    bind_vps_operation,
    request_digest,
)
from odoo_forge_docker.vps.transport import OpenSshTarget, OpenSshTransport
from tests.adapters.test_vps_provider import Store

# The fixed remote argv below is intentionally readable in this bounded slice.
# fmt: off
# ruff: noqa: E501, I001

pytestmark = pytest.mark.integration


def _owned(operation: DurableOperationIdentity, kind: str, identifier: str) -> OwnershipRecord:
    return OwnershipRecord(
        ref=ResourceRef(identifier=identifier, resource_kind=kind, ownership=ResourceOwnership.CREATED),
        receipt=OwnershipReceipt(operation=operation, owned_resource_ids=(identifier,)),
    )


class _Sshd:
    def __init__(self, root: Path) -> None:
        self.port = self._free_port()
        self.user = getpass.getuser()
        self.identity = root / "identity"
        self.host_key = root / "host_key"
        self.config = root / "sshd_config"
        self.process: subprocess.Popen[bytes] | None = None
        for path in (self.identity, self.host_key):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
        (root / "authorized_keys").write_text(self.identity.with_name("identity.pub").read_text())
        self.config.write_text(
            f"""Port {self.port}
ListenAddress 127.0.0.1
HostKey {self.host_key}
AuthorizedKeysFile {root / 'authorized_keys'}
AllowUsers {self.user}
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
StrictModes no
LogLevel QUIET
Subsystem sftp internal-sftp
"""
        )
        subprocess.run(["/usr/bin/sshd", "-t", "-f", str(self.config)], check=True)

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @property
    def target(self) -> VpsTargetIdentity:
        host_line = self.host_key.with_suffix(".pub").read_text().strip()
        return VpsTargetIdentity("127.0.0.1", self.user, self.port, f"[127.0.0.1]:{self.port} {host_line}")

    def transport(self) -> OpenSshTransport:
        target = self.target
        return OpenSshTransport(OpenSshTarget(target.host, target.user, target.port, target.host_key, self.identity.read_text()), timeout=5)

    def start(self) -> None:
        self.process = subprocess.Popen(["/usr/bin/sshd", "-D", "-e", "-f", str(self.config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        transport = self.transport()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("disposable sshd exited during startup")
            try:
                transport.run(("true",))
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("disposable sshd did not become ready")

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.process = None


class _RemoteHarness:
    def __init__(self, sshd: _Sshd) -> None:
        self.sshd = sshd
        self.resources: list[str] = []
        self.networks: list[str] = []
        self.volumes: list[str] = []

    @property
    def target(self) -> VpsTargetIdentity:
        return self.sshd.target

    def transport(self) -> OpenSshTransport:
        return self.sshd.transport()

    def cleanup(self) -> None:
        if self.sshd.process is None:
            self.sshd.start()
        errors: list[Exception] = []
        for name in reversed(self.resources):
            command = (
                ("docker", "network", "rm", name)
                if name in self.networks
                else ("docker", "volume", "rm", name)
                if name in self.volumes
                else ("docker", "rm", "-f", name)
            )
            try:
                self.transport().run(command, mutating=True)
            except Exception as exc:
                errors.append(exc)
        self.resources.clear()
        self.networks.clear()
        self.volumes.clear()
        if errors:
            raise errors[0]


def _require_runtime() -> None:
    for executable in ("/usr/bin/docker", "/usr/bin/sshd", "/usr/bin/ssh-keygen"):
        if not Path(executable).exists():
            pytest.skip(f"disposable VPS prerequisite unavailable: {executable}")
    if subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, check=False).returncode:
        pytest.skip("disposable VPS prerequisite unavailable: Docker daemon is unreachable")
    if subprocess.run(["docker", "image", "inspect", "caddy:2-alpine"], capture_output=True, text=True, check=False).returncode:
        pytest.skip("disposable VPS prerequisite unavailable: pinned Caddy image is missing")


@pytest.fixture
def remote(tmp_path: Path) -> Iterator[_RemoteHarness]:
    _require_runtime()
    sshd = _Sshd(tmp_path)
    sshd.start()
    harness = _RemoteHarness(sshd)
    try:
        yield harness
    finally:
        harness.cleanup()
        sshd.stop()


def _plan(suffix: str, *, with_volume: bool = False) -> tuple[BackendPlan, ProjectScope]:
    project = f"u5-{suffix}"
    scope = ProjectScope(tenant=TenantId(value="tenant-u5"), project_id=project)
    labels = {"com.odoo-forge.project": project, "com.odoo-forge.instance": "default", "com.odoo-forge.managed": "true"}
    network = NetworkSpec(name=f"odoo-forge-{project}", labels=labels)
    volumes = [VolumeSpec(name=f"{network.name}-data", labels=labels)] if with_volume else []
    common: Any = {"network": network.name, "env": {}}
    postgres = ContainerSpec(name=f"{network.name}-db", image="caddy:2-alpine", role="postgres", labels={**labels, "com.odoo-forge.role": "postgres"}, volumes=volumes, **common)
    odoo = ContainerSpec(name=f"{network.name}-odoo", image="caddy:2-alpine", role="odoo", labels={**labels, "com.odoo-forge.role": "odoo"}, ports={"80": 80}, **common)
    return BackendPlan(network=network, volumes=volumes, postgres=postgres, odoo=odoo, postgres_credentials=CredentialHandle("integration/ssh")), scope


def _managed_odoo_image() -> str:
    image = os.environ.get("ODOO_FORGE_TEST_ODOO_IMAGE", "ghcr.io/aparragithub/odoo-ce:19")
    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, check=False)
    if inspected.returncode != 0:
        pytest.skip(f"repository-approved Odoo image unavailable: {image}")
    metadata = json.loads(inspected.stdout)[0]
    labels = metadata["Config"]["Labels"]
    assert labels["org.opencontainers.image.source"] == "https://github.com/aparragithub/odoo-forge"
    assert labels["org.opencontainers.image.version"] == "19.0"
    assert labels["org.opencontainers.image.revision"]
    repository = image.partition("@")[0]
    if ":" in repository.rsplit("/", 1)[-1]:
        repository = repository.rsplit(":", 1)[0]
    prefix = f"{repository}@sha256:"
    digests = cast(list[str], metadata["RepoDigests"])
    return next(digest for digest in digests if digest.startswith(prefix))


def _normal_managed_plan(suffix: str) -> tuple[BackendPlan, ProjectScope, str]:
    project = f"u9-{suffix}"
    scope = ProjectScope(tenant=TenantId(value="tenant-u9"), project_id=project)
    manifest = Manifest(
        name=project,
        odoo_version="19.0",
        edition="community",
        client=Client(addons_path=Path("/tmp/odoo-forge-u9-addons")),
        backend=BackendConfig(odoo=OdooBackendConfig(http_port=80)),
    )
    image = _managed_odoo_image()
    plan = plan_backend(
        manifest,
        MountPlanningView(mounts=()),
        odoo_image=image,
        credentials=BackendCredentialBindings(odoo_db_password=CredentialHandle("integration/odoo")),
        postgres_credentials=CredentialHandle("integration/postgres"),
    )
    assert plan.odoo.ports == {"8069": 80, "8072": None}
    return plan, scope, image


def _bound(verb: str, payload: object, scope: ProjectScope, remote: _RemoteHarness, store: Store, operation_id: str) -> Any:
    handles = (
        (*payload.odoo.secret_env.values(), *([payload.postgres_credentials] if payload.postgres_credentials else ()))
        if isinstance(payload, BackendPlan)
        else (CredentialHandle("integration/ssh"),)
    )
    identity = DurableOperationIdentity(operation_id=operation_id, request_digest="pending")
    digest = request_digest(verb, scope, remote.target, handles, payload)
    binding = VpsOperationBinding(scope=scope, operation=identity.model_copy(update={"request_digest": digest}), verb=verb, ownership=(), target=remote.target, credential_handles=handles)
    if isinstance(payload, BackendPlan):
        for resource in (payload.network.name, *(volume.name for volume in payload.volumes), payload.postgres.name, payload.odoo.name):
            if resource not in remote.resources:
                remote.resources.append(resource)
        if payload.network.name not in remote.networks:
            remote.networks.append(payload.network.name)
        for volume in payload.volumes:
            if volume.name not in remote.volumes:
                remote.volumes.append(volume.name)
    return bind_vps_operation(binding, store=cast(Any, store), mechanics=RemoteDockerMechanics(remote.target, remote.sshd.identity.read_text(), credential_resolver=lambda handle: "unit9-db-password" if str(handle) in {"integration/odoo", "integration/postgres"} else str(handle)))


def _request(ref: InstanceRef, scope: ProjectScope, operation: DurableOperationIdentity) -> ExposureRequest:
    deployment = DeploymentSpec(pointer=InstancePointer(scope=scope, instance_id=InstanceId(value="default")), resource=ResourceRef(identifier=ref.network, resource_kind="instance", ownership=ResourceOwnership.CREATED), runtime=OdooRuntimeIntent(odoo_version="19"), exposure=ExposureIntent(hostname="localhost", protocol=RouteProtocol.HTTPS, dns=RequirementPolicy.REQUIRED, tls=RequirementPolicy.REQUIRED))
    return ExposureRequest(instance=ref, deployment=deployment, scope=scope, operation=operation)


def _relabel(plan: BackendPlan, scope: ProjectScope) -> BackendPlan:
    def labels(existing: dict[str, str]) -> dict[str, str]:
        return {**existing, "com.odoo-forge.project": scope.project_id}

    return plan.model_copy(
        update={
            "network": plan.network.model_copy(update={"labels": labels(plan.network.labels)}),
            "postgres": plan.postgres.model_copy(update={"labels": labels(plan.postgres.labels)}),
            "odoo": plan.odoo.model_copy(update={"labels": labels(plan.odoo.labels)}),
        }
    )


def test_strict_pinned_transfer_redacts_and_cleans_secret(remote: _RemoteHarness) -> None:
    secret = uuid.uuid4().hex
    remote_path = f"/tmp/u4-secret-{uuid.uuid4().hex}"
    try:
        result = remote.transport().upload_secret(secret, remote_path)
        digest = remote.transport().run(("sha256sum", remote_path)).stdout.split()[0]
        mode = remote.transport().run(("stat", "-c", "%a", remote_path)).stdout.strip()
        assert digest == hashlib.sha256(secret.encode()).hexdigest()
        assert mode == "600"
        assert secret not in result.stdout and secret not in result.stderr
    finally:
        remote.transport().run(("rm", "-f", remote_path), mutating=True)


def test_disposable_cleanup_removes_networks_with_network_command(remote: _RemoteHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[str, ...], bool]] = []

    class _RecordingTransport:
        def run(self, argv: tuple[str, ...], *, mutating: bool = False) -> object:
            calls.append((argv, mutating))
            return object()

    monkeypatch.setattr(remote, "transport", lambda: _RecordingTransport())
    remote.resources.append("odoo-forge-u5-cleanup")
    remote.networks.append("odoo-forge-u5-cleanup")
    remote.cleanup()
    assert calls == [(("docker", "network", "rm", "odoo-forge-u5-cleanup"), True)]


def test_real_runtime_labels_health_http_dns_and_deferred_tls(remote: _RemoteHarness) -> None:
    plan, scope = _plan(uuid.uuid4().hex[:8])
    store = Store()
    ref = _bound("run", plan, scope, remote, store, "u5-run").run(plan)
    entries = cast(list[dict[str, Any]], json.loads(remote.transport().run(("docker", "inspect", ref.network, ref.postgres_container, ref.odoo_container)).stdout))
    labels = [entry["Config"]["Labels"] for entry in entries if entry.get("Config")]
    assert all(item["com.odoo-forge.project"] == scope.project_id for item in labels)
    assert {item["com.odoo-forge.role"] for item in labels} == {"postgres", "odoo"}
    assert all(item["com.odoo-forge.managed"] == "true" for item in labels)
    odoo = next(entry for entry in entries if entry["Name"].lstrip("/") == ref.odoo_container)
    assert odoo["NetworkSettings"]["Ports"]["80/tcp"][0]["HostPort"] == "80"
    request = _request(ref, scope, DurableOperationIdentity(operation_id="u5-expose", request_digest="pending"))
    exposure = _bound("reconcile", request, scope, remote, store, "u5-expose").reconcile(request)
    assert isinstance(exposure, ExposureResult)
    assert exposure.ready and exposure.tls_ready is False and exposure.tls_status.value == "deferred"
    assert exposure.routing_status.value == "verified" and exposure.dns_status.value == "verified"
    assert any(str(item[4][0]) == "127.0.0.1" for item in socket.getaddrinfo("127.0.0.1", 80))
    assert urlopen("http://127.0.0.1/", timeout=5).status == 200


def test_normal_plan_publishes_http_80_and_proves_managed_odoo_readiness(remote: _RemoteHarness) -> None:
    plan, scope, image = _normal_managed_plan(uuid.uuid4().hex[:8])
    store = Store()
    try:
        ref = _bound("run", plan, scope, remote, store, "u9-managed").run(plan)
    except RuntimeError:
        remote.resources.clear()
        remote.networks.clear()
        remote.volumes.clear()
        raise
    entries = cast(
        list[dict[str, Any]],
        json.loads(remote.transport().run(("docker", "inspect", ref.odoo_container)).stdout),
    )
    odoo = entries[0]
    assert odoo["Config"]["Image"] == image
    assert odoo["NetworkSettings"]["Ports"]["8069/tcp"][0]["HostPort"] == "80"
    assert urlopen("http://127.0.0.1/web/health", timeout=5).status == 200

    request = _request(ref, scope, DurableOperationIdentity(operation_id="u9-expose", request_digest="pending"))
    exposure = _bound("reconcile", request, scope, remote, store, "u9-expose").reconcile(request)
    assert isinstance(exposure, ExposureResult)
    assert exposure.ready and exposure.tls_ready is False
    assert exposure.routing_status.value == "verified" and exposure.dns_status.value == "verified"


def test_production_unmanaged_live_resource_is_rejected_without_mutation(remote: _RemoteHarness) -> None:
    plan, scope, image = _normal_managed_plan(uuid.uuid4().hex[:8])
    live_labels = {
        **plan.odoo.labels,
        "com.odoo-forge.tenant": scope.tenant.value,
        "com.odoo-forge.pointer": f"{scope.tenant.value}/{scope.project_id}/default",
    }
    live_labels.pop("com.odoo-forge.role")
    network_args = ["docker", "network", "create"]
    for key, value in {**plan.network.labels, **{key: live_labels[key] for key in ("com.odoo-forge.tenant", "com.odoo-forge.pointer")}}.items():
        network_args.extend(("--label", f"{key}={value}"))
    remote.transport().run((*network_args, plan.network.name), mutating=True)
    container_args = ["docker", "create", "--name", plan.odoo.name, "--network", plan.network.name]
    for key, value in live_labels.items():
        container_args.extend(("--label", f"{key}={value}"))
    remote.transport().run((*container_args, image), mutating=True)
    remote.resources.extend((plan.network.name, plan.odoo.name))
    remote.networks.append(plan.network.name)
    before = remote.transport().run(("docker", "inspect", plan.network.name, plan.odoo.name)).stdout
    try:
        store = Store()
        adapter = _bound("run", plan, scope, remote, store, "u9-unmanaged")
        with pytest.raises(ValueError, match="scope"):
            adapter.run(plan)

        after = remote.transport().run(("docker", "inspect", plan.network.name, plan.odoo.name)).stdout
        assert after == before
        assert remote.transport().run(("docker", "ps", "-aq", "--filter", f"name=^{plan.postgres.name}$")).stdout == ""
    finally:
        remote.resources[:] = [name for name in remote.resources if name in {plan.network.name, plan.odoo.name}]
        remote.networks[:] = [plan.network.name]
        remote.volumes.clear()


def test_production_runtime_replay_does_not_create_duplicate_resources(remote: _RemoteHarness) -> None:
    plan, scope = _plan(uuid.uuid4().hex[:8])
    store = Store()
    ref = _bound("run", plan, scope, remote, store, "u5-replay").run(plan)
    calls_before = remote.transport().run(("docker", "ps", "-aq", "--filter", f"name={ref.odoo_container}")).stdout
    replay = _bound("run", plan, scope, remote, store, "u5-replay").run(plan)
    calls_after = remote.transport().run(("docker", "ps", "-aq", "--filter", f"name={ref.odoo_container}")).stdout
    assert replay == ref
    assert calls_after == calls_before
    assert store.records["u5-replay"].lifecycle is LifecycleState.SUCCEEDED


def test_production_interrupted_replay_recreates_missing_runtime_completely(remote: _RemoteHarness) -> None:
    plan, scope = _plan(uuid.uuid4().hex[:8], with_volume=True)
    store = Store()
    adapter = _bound("run", plan, scope, remote, store, "u8-replay")
    record = store.create_or_load(adapter._binding.operation)
    store.mark_reconciliation_required(adapter._binding.operation.operation_id, record.revision)

    ref = adapter.run(plan)

    entries = cast(
        list[dict[str, Any]],
        json.loads(
            remote.transport()
            .run(("docker", "inspect", ref.network, plan.volumes[0].name, ref.postgres_container, ref.odoo_container))
            .stdout
        ),
    )
    assert {entry["Name"].lstrip("/") for entry in entries} == {
        ref.network,
        plan.volumes[0].name,
        ref.postgres_container,
        ref.odoo_container,
    }
    assert all(
        entry.get("Config", entry).get("Labels", {}).get("com.odoo-forge.operation") == "u8-replay"
        for entry in entries
    )
    assert store.records["u8-replay"].identity == adapter._binding.operation
    assert store.records["u8-replay"].lifecycle is LifecycleState.SUCCEEDED

    replay = _bound("run", plan, scope, remote, store, "u8-replay").run(plan)
    assert replay == ref


def test_production_rejects_cross_project_name_collision_without_mutation(remote: _RemoteHarness) -> None:
    plan_a, scope_a = _plan(uuid.uuid4().hex[:8])
    store = Store()
    ref_a = _bound("run", plan_a, scope_a, remote, store, "u6-owner").run(plan_a)
    plan_b, scope_b = _plan(uuid.uuid4().hex[:8])
    plan_b = _relabel(plan_a, ProjectScope(tenant=TenantId(value="tenant-u6-b"), project_id="u6-project-b"))
    scope_b = ProjectScope(tenant=TenantId(value="tenant-u6-b"), project_id="u6-project-b")

    with pytest.raises(ValueError, match="scope"):
        _bound("run", plan_b, scope_b, remote, store, "u6-collision").run(plan_b)

    live = cast(list[dict[str, Any]], json.loads(remote.transport().run(("docker", "inspect", ref_a.network)).stdout))[0]
    assert live["Labels"]["com.odoo-forge.project"] == scope_a.project_id
    assert live["Labels"]["com.odoo-forge.tenant"] == scope_a.tenant.value


def test_production_reconciles_partial_runtime_without_duplicate_resources(remote: _RemoteHarness) -> None:
    runtime_plan, scope = _plan(uuid.uuid4().hex[:8])
    store = Store()
    labels = {
        **runtime_plan.network.labels,
        "com.odoo-forge.tenant": scope.tenant.value,
        "com.odoo-forge.pointer": f"{scope.tenant.value}/{scope.project_id}/default",
    }
    args = ["docker", "network", "create"]
    for key, value in labels.items():
        args.extend(("--label", f"{key}={value}"))
    remote.transport().run((*args, runtime_plan.network.name), mutating=True)
    container_labels = {**runtime_plan.postgres.labels, **labels, "com.odoo-forge.role": "postgres"}
    args = ["docker", "run", "-d", "--name", runtime_plan.postgres.name, "--network", runtime_plan.network.name]
    for key, value in container_labels.items():
        args.extend(("--label", f"{key}={value}"))
    remote.transport().run((*args, runtime_plan.postgres.image), mutating=True)
    remote.resources.extend((runtime_plan.network.name, runtime_plan.postgres.name))
    remote.networks.append(runtime_plan.network.name)
    before = remote.transport().run(("docker", "ps", "-aq", "--filter", f"name={runtime_plan.odoo.name}")).stdout

    ref = _bound("run", runtime_plan, scope, remote, store, "u6-partial").run(runtime_plan)

    after = remote.transport().run(("docker", "ps", "-aq", "--filter", f"name={runtime_plan.odoo.name}")).stdout
    assert before == ""
    assert after.strip()
    assert ref.odoo_container == runtime_plan.odoo.name


def test_post_create_failure_compensates_created_runtime_only(remote: _RemoteHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, scope = _plan(uuid.uuid4().hex[:8])
    store = Store()
    adapter = _bound("run", plan, scope, remote, store, "u7-failure")
    mechanics = cast(RemoteDockerMechanics, adapter._mechanics)
    monkeypatch.setattr(mechanics, "runtime_ready", lambda ref: False)

    with pytest.raises(RuntimeError, match="not ready"):
        adapter.run(plan)

    for identifier in (plan.network.name, plan.postgres.name, plan.odoo.name):
        assert not remote.transport().run(("docker", "ps", "-aq", "--filter", f"name=^{identifier}$")).stdout.strip()
    assert not remote.transport().run(("docker", "network", "ls", "-q", "--filter", f"name=^{plan.network.name}$")).stdout.strip()
    remote.resources.clear()
    remote.networks.clear()


def test_production_exposure_failure_retains_terminal_created_receipt(
    remote: _RemoteHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, scope = _plan(uuid.uuid4().hex[:8])
    store = Store()
    ref = _bound("run", plan, scope, remote, store, "u10-runtime").run(plan)
    request = _request(
        ref,
        scope,
        DurableOperationIdentity(operation_id="u10-exposure-failure", request_digest="pending"),
    )
    adapter = _bound("reconcile", request, scope, remote, store, "u10-exposure-failure")
    mechanics = cast(RemoteDockerMechanics, adapter._mechanics)
    monkeypatch.setattr(mechanics, "verify_http", lambda _hostname: (_ for _ in ()).throw(RuntimeError("injected exposure failure")))

    with pytest.raises(RuntimeError, match="injected exposure failure"):
        adapter.reconcile(request)

    record = store.records["u10-exposure-failure"]
    assert record.lifecycle is LifecycleState.FAILED
    assert record.terminal_commit is not None
    assert any(evidence.event == "ownership_verified" for evidence in record.terminal_commit.evidence)
    assert all("unit9-db-password" not in str(evidence) for evidence in record.recovery_evidence)
    assert remote.transport().run(("docker", "ps", "-aq", "--filter", f"name=^{ref.odoo_container}$")).stdout.strip()
    remote.resources.clear()
    remote.networks.clear()
    remote.volumes.clear()


def test_production_stop_stops_containers_and_preserves_network_and_volumes(
    remote: _RemoteHarness,
) -> None:
    plan, scope = _plan(uuid.uuid4().hex[:8], with_volume=True)
    plan = plan.model_copy(update={"odoo": plan.odoo.model_copy(update={"ports": {}})})
    store = Store()
    run_adapter = _bound("run", plan, scope, remote, store, "u11-run")
    ref = run_adapter.run(plan)
    stop_adapter = _bound("stop", ref, scope, remote, store, "u11-stop")

    stop_adapter.stop(ref)

    entries = cast(
        list[dict[str, Any]],
        json.loads(
            remote.transport()
            .run(("docker", "inspect", ref.network, plan.volumes[0].name, ref.postgres_container, ref.odoo_container))
            .stdout
        ),
    )
    by_name = {entry["Name"].lstrip("/"): entry for entry in entries}
    assert by_name[ref.network]["Name"].lstrip("/") == ref.network
    assert by_name[plan.volumes[0].name]["Name"] == plan.volumes[0].name
    assert all(not by_name[name]["State"]["Running"] for name in (ref.postgres_container, ref.odoo_container))
    assert all(
        remote.transport().run(("docker", "ps", "-aq", "--filter", f"name=^{name}$")).stdout.strip()
        for name in (ref.postgres_container, ref.odoo_container)
    )
    assert store.records["u11-stop"].lifecycle is LifecycleState.SUCCEEDED
