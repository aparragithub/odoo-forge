"""Strict-TDD behavior tests for the bound VPS provider."""

# Keep this focused fake-mechanics slice within the Unit 3 authored-line budget.
# fmt: off
# ruff: noqa: E501, I001

from dataclasses import dataclass, replace
import json
from types import SimpleNamespace
from typing import Any, cast

import pytest

from odoo_forge.backend.plan import BackendPlan, ContainerSpec, Mount, NetworkSpec, VolumeSpec
from odoo_forge.backend.status import InstanceRef
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.deployment_spec.types import (
    DeploymentSpec,
    ExposureIntent,
    OdooRuntimeIntent,
    RequirementPolicy,
    RouteProtocol,
)
from odoo_forge.durable_operations.types import DurableOperationIdentity, LifecycleState, OperationRevision
from odoo_forge.exposure.types import ExposureCheckStatus, ExposureOutcome, ExposureRequest
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.ports.durable_operation_store import DurableOperationRecord
from odoo_forge.resource_ownership.types import OwnershipReceipt, OwnershipRecord, ResourceOwnership, ResourceRef
from odoo_forge.tenancy.types import ProjectScope, TenantId
from odoo_forge_docker.vps import provider as vps_provider
from odoo_forge_docker.vps.provider import (
    RemoteDockerMechanics,
    VpsOperationBinding,
    VpsTargetIdentity,
    bind_vps_operation,
)


class Store:
    def __init__(self) -> None:
        self.records: dict[str, DurableOperationRecord] = {}

    def create_or_load(self, identity: DurableOperationIdentity) -> DurableOperationRecord:
        return self.records.setdefault(identity.operation_id, DurableOperationRecord(identity=identity, revision=OperationRevision(value=0)))

    def save_checkpoint(self, operation_id: str, expected_revision: OperationRevision, checkpoint: Any) -> DurableOperationRecord:
        record = replace(self.records[operation_id], revision=OperationRevision(value=checkpoint.revision.value + 1), lifecycle=LifecycleState.IN_PROGRESS, checkpoint=checkpoint, recovery_evidence=self.records[operation_id].recovery_evidence + (checkpoint.evidence,))
        self.records[operation_id] = record
        return record

    def mark_reconciliation_required(self, operation_id: str, expected_revision: OperationRevision) -> DurableOperationRecord:
        record = replace(self.records[operation_id], revision=OperationRevision(value=expected_revision.value + 1), lifecycle=LifecycleState.RECONCILIATION_REQUIRED)
        self.records[operation_id] = record
        return record

    def commit_terminal(self, operation_id: str, bundle: Any) -> DurableOperationRecord:
        record = replace(self.records[operation_id], revision=OperationRevision(value=record_revision(self.records[operation_id]) + 1), lifecycle=bundle.outcome, terminal_commit=bundle, recovery_evidence=bundle.evidence)
        self.records[operation_id] = record
        return record


def record_revision(record: DurableOperationRecord) -> int:
    return record.revision.value

class Unknown(RuntimeError):
    state = "unknown_post_mutation"


class RecordingSsh:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], *, mutating: bool = False) -> SimpleNamespace:
        self.commands.append(command)
        return SimpleNamespace(stdout="")


class InspectingSsh(RecordingSsh):
    def __init__(self, entries: dict[str, dict[str, Any]]) -> None:
        super().__init__()
        self.entries = entries
        self.uploads: list[str] = []

    def run(self, command: tuple[str, ...], *, mutating: bool = False) -> SimpleNamespace:
        self.commands.append(command)
        if len(command) >= 6 and command[-2] == "--filter":
            name = command[-1].removeprefix("name=^").removesuffix("$")
            return SimpleNamespace(stdout="resource-id\n" if name in self.entries else "")
        if command[:2] == ("docker", "inspect"):
            entries = [self.entries[name] for name in command[2:] if name in self.entries]
            return SimpleNamespace(stdout=json.dumps(entries) if entries else "")
        return SimpleNamespace(stdout="")

    def upload_secret(self, secret: str, remote_path: str, *, mutating: bool = True) -> SimpleNamespace:
        self.uploads.append(remote_path)
        return SimpleNamespace(stdout="", stderr="")


def inspected(name: str, labels: dict[str, str], *, healthy: bool = True) -> dict[str, Any]:
    return {
        "Name": f"/{name}",
        "Config": {"Labels": labels},
        "State": {
            "Running": True,
            "Health": {"Status": "healthy" if healthy else "unhealthy"},
        },
    }


def test_remote_runtime_publishes_http_at_creation_without_post_start_update() -> None:
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = RecordingSsh()
    mechanics._ssh = cast(Any, ssh)
    runtime_plan = plan()
    runtime_plan = runtime_plan.model_copy(
        update={
            "odoo": runtime_plan.odoo.model_copy(update={"ports": {"8069": 80}}),
        }
    )

    mechanics.ensure_runtime(runtime_plan, DurableOperationIdentity(operation_id="u5", request_digest="d"))

    odoo_run = next(command for command in ssh.commands if command[0:3] == ("docker", "run", "-d") and runtime_plan.odoo.name in command)
    assert "127.0.0.1:80:8069" in odoo_run
    assert all("update" not in command for command in ssh.commands)


def test_remote_stop_stops_containers_but_preserves_network_and_volume_kinds() -> None:
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = RecordingSsh()
    mechanics._ssh = cast(Any, ssh)
    ref = InstanceRef(
        project="alpha",
        instance="one",
        network="net-alpha",
        postgres_container="db",
        odoo_container="odoo",
    )

    mechanics.stop(ref)

    assert ssh.commands == [
        ("docker", "stop", "odoo"),
        ("docker", "stop", "db"),
    ]
    assert all(command[-1] != ref.network for command in ssh.commands)
    assert all(command[1:3] != ("volume", "rm") for command in ssh.commands)


def test_remote_http_verification_contacts_the_real_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    mechanics = object.__new__(RemoteDockerMechanics)
    requests: list[tuple[str, float]] = []

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def open_endpoint(url: str, *, timeout: float) -> Response:
        requests.append((url, timeout))
        return Response()

    monkeypatch.setattr(vps_provider, "urlopen", open_endpoint, raising=False)

    assert mechanics.verify_http("vps.example.test") is True
    assert requests == [("http://vps.example.test/", 5.0)]


def test_remote_http_verification_rejects_non_success_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    mechanics = object.__new__(RemoteDockerMechanics)

    class Response:
        status = 503

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(vps_provider, "urlopen", lambda *args, **kwargs: Response(), raising=False)

    assert mechanics.verify_http("vps.example.test") is False


def _managed_odoo_inspect() -> dict[str, Any]:
    entry = inspected("net-alpha-one-odoo", {"com.odoo-forge.managed": "true"})
    entry["Config"]["Image"] = "ghcr.io/aparragithub/odoo-ce@sha256:" + "a" * 64
    return entry


def test_managed_odoo_readiness_requires_the_real_health_endpoint() -> None:
    mechanics = object.__new__(RemoteDockerMechanics)
    calls: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], *, mutating: bool = False) -> str:
        calls.append(command)
        if command[:2] == ("docker", "inspect"):
            return json.dumps([_managed_odoo_inspect()])
        raise RuntimeError("Odoo health endpoint is not ready")

    mechanics._run = run  # type: ignore[assignment]

    assert mechanics.runtime_ready(
        InstanceRef(
            project="alpha",
            instance="one",
            network="net-alpha",
            postgres_container="db",
            odoo_container="net-alpha-one-odoo",
        )
    ) is False
    assert any(command[:2] == ("docker", "inspect") for command in calls)
    assert any(command[:2] == ("docker", "exec") for command in calls)


def test_managed_odoo_readiness_accepts_a_successful_health_endpoint() -> None:
    mechanics = object.__new__(RemoteDockerMechanics)

    def run(command: tuple[str, ...], *, mutating: bool = False) -> str:
        if command[:2] == ("docker", "inspect"):
            return json.dumps([_managed_odoo_inspect()])
        if command[:2] == ("docker", "exec"):
            return "Odoo Server is ready"
        raise AssertionError(command)

    mechanics._run = run  # type: ignore[assignment]

    assert mechanics.runtime_ready(
        InstanceRef(
            project="alpha",
            instance="one",
            network="net-alpha",
            postgres_container="db",
            odoo_container="net-alpha-one-odoo",
        )
    ) is True


def test_production_scope_collision_rejects_before_any_mutation() -> None:
    runtime_plan = plan()
    collision = inspected(
        runtime_plan.network.name,
        {
            "com.odoo-forge.managed": "true",
            "com.odoo-forge.tenant": "other-tenant",
            "com.odoo-forge.project": runtime_plan.network.labels["com.odoo-forge.project"],
            "com.odoo-forge.instance": "one",
        },
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({runtime_plan.network.name: collision})
    mechanics._ssh = cast(Any, ssh)
    store = Store()
    binding = VpsOperationBinding(
        scope=scope(),
        operation=DurableOperationIdentity(operation_id="scope", request_digest="pending"),
        verb="run",
        ownership=(),
        target=VpsTargetIdentity("vps.example.test", "forge", 22, "key"),
        credential_handles=(CredentialHandle("pg"),),
    )
    adapter = bind_vps_operation(binding, store=cast(Any, store), mechanics=cast(Any, mechanics))
    operation = binding.operation.model_copy(update={"request_digest": adapter.request_digest(runtime_plan)})
    adapter = bind_vps_operation(replace(binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    with pytest.raises(ValueError, match="scope"):
        adapter.run(runtime_plan)

    assert all(command[1:3] not in (("network", "create"), ("volume", "create")) for command in ssh.commands)
    assert all(command[1] != "run" for command in ssh.commands)


def test_live_container_without_managed_role_rejects_before_any_mutation() -> None:
    runtime_plan = plan()
    live_labels = {
        **runtime_plan.network.labels,
        "com.odoo-forge.tenant": "tenant",
        "com.odoo-forge.pointer": "tenant/alpha/one",
    }
    ssh = InspectingSsh(
        {
            runtime_plan.network.name: inspected(runtime_plan.network.name, live_labels),
            runtime_plan.odoo.name: inspected(runtime_plan.odoo.name, live_labels),
        }
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    mechanics._ssh = cast(Any, ssh)
    store = Store()
    binding = VpsOperationBinding(
        scope=scope(),
        operation=DurableOperationIdentity(operation_id="unmanaged", request_digest="pending"),
        verb="run",
        ownership=(),
        target=VpsTargetIdentity("vps.example.test", "forge", 22, "key"),
        credential_handles=(CredentialHandle("pg"),),
    )
    adapter = bind_vps_operation(binding, store=cast(Any, store), mechanics=cast(Any, mechanics))
    operation = binding.operation.model_copy(update={"request_digest": adapter.request_digest(runtime_plan)})
    adapter = bind_vps_operation(replace(binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    with pytest.raises(ValueError, match="scope"):
        adapter.run(runtime_plan)

    assert all(command[1:3] != ("network", "create") for command in ssh.commands)
    assert all(command[1] != "run" for command in ssh.commands)


def test_production_runtime_realizes_plan_details_without_secret_values() -> None:
    runtime_plan = plan().model_copy(
        update={
            "volumes": [VolumeSpec(name="pg-volume", labels={"role": "postgres"})],
            "postgres": plan().postgres.model_copy(
                update={"volumes": [VolumeSpec(name="pg-volume", labels={"role": "postgres"})]}
            ),
            "odoo": plan().odoo.model_copy(
                update={
                    "env": {"APP_MODE": "managed"},
                    "secret_env": {"DB_PASSWORD": CredentialHandle("secret-handle")},
                    "mounts": [Mount(root="custom", host_path="/srv/addons", container_path="/mnt/addons", read_only=True)],
                }
            ),
        }
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({})
    mechanics._ssh = cast(Any, ssh)
    mechanics._credential_resolver = lambda handle: str(handle)

    mechanics.ensure_runtime(runtime_plan, DurableOperationIdentity(operation_id="plan", request_digest="digest"))

    commands = [" ".join(command) for command in ssh.commands]
    odoo_run = next(command for command in commands if "docker run -d" in command and runtime_plan.odoo.name in command)
    assert "APP_MODE=managed" in odoo_run
    assert "pg-volume:/var/lib/postgresql/data" in next(command for command in commands if "docker run -d" in command and runtime_plan.postgres.name in command)
    assert "/srv/addons:/mnt/addons:ro" in odoo_run
    assert "--env-file /tmp/odoo-forge-secret-" in odoo_run
    assert "secret-handle" not in odoo_run
    assert ssh.uploads


def test_managed_odoo_secret_uses_entrypoint_compatible_env_file() -> None:
    runtime_plan = plan().model_copy(
        update={
            "odoo": plan().odoo.model_copy(
                update={
                    "image": "ghcr.io/aparragithub/odoo-ce@sha256:" + "a" * 64,
                    "secret_env": {"DB_PASSWORD": CredentialHandle("secret-handle")},
                }
            )
        }
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({})
    mechanics._ssh = cast(Any, ssh)
    mechanics._credential_resolver = lambda _handle: "db-password"

    mechanics.ensure_runtime(runtime_plan, DurableOperationIdentity(operation_id="env-file", request_digest="digest"))

    commands = [" ".join(command) for command in ssh.commands]
    odoo_run = next(command for command in commands if "docker run -d" in command and runtime_plan.odoo.name in command)
    assert "--env-file /tmp/odoo-forge-secret-" in odoo_run
    assert "DB_PASSWORD_FILE=/run/secrets/DB_PASSWORD" not in odoo_run
    assert "db-password" not in odoo_run


def test_new_managed_odoo_runtime_initializes_base_before_readiness() -> None:
    pg_volume = VolumeSpec(name="pg-volume", labels={"role": "postgres"})
    filestore_volume = VolumeSpec(name="filestore-volume", labels={"role": "odoo"})
    runtime_plan = plan().model_copy(
        update={
            "volumes": [pg_volume, filestore_volume],
            "postgres": plan().postgres.model_copy(update={"volumes": [pg_volume]}),
            "odoo": plan().odoo.model_copy(
                update={
                    "image": "ghcr.io/aparragithub/odoo-ce@sha256:" + "a" * 64,
                    "env": {"POSTGRES_DB": "alpha"},
                    "volumes": [filestore_volume],
                }
            ),
        }
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({})
    original_run = ssh.run

    def run(command: tuple[str, ...], *, mutating: bool = False) -> SimpleNamespace:
        if command[:2] == ("docker", "wait"):
            ssh.commands.append(command)
            return SimpleNamespace(stdout="0")
        return original_run(command, mutating=mutating)

    ssh.run = run  # type: ignore[method-assign]
    mechanics._ssh = cast(Any, ssh)
    mechanics._credential_resolver = lambda _handle: "db-password"

    mechanics.ensure_runtime(runtime_plan, DurableOperationIdentity(operation_id="bootstrap", request_digest="digest"))

    bootstrap_run = next(
        command
        for command in ssh.commands
        if command[:3] == ("docker", "run", "-d") and f"{runtime_plan.odoo.name}-bootstrap" in command
    )
    assert "-i" in bootstrap_run and "base" in bootstrap_run
    assert "--stop-after-init" in bootstrap_run and "--no-http" in bootstrap_run
    assert ("docker", "wait", f"{runtime_plan.odoo.name}-bootstrap") in ssh.commands


def test_production_partial_discovery_adopts_live_resources_and_creates_only_missing() -> None:
    runtime_plan = plan()
    labels = {**runtime_plan.network.labels, "com.odoo-forge.role": "postgres"}
    ssh = InspectingSsh(
        {
            runtime_plan.network.name: inspected(runtime_plan.network.name, runtime_plan.network.labels),
            runtime_plan.postgres.name: inspected(runtime_plan.postgres.name, labels),
        }
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    mechanics._ssh = cast(Any, ssh)

    owned_resources = mechanics.ensure_runtime(
        runtime_plan, DurableOperationIdentity(operation_id="partial", request_digest="digest")
    )

    assert {item.ref.identifier for item in owned_resources} == {
        runtime_plan.network.name,
        runtime_plan.postgres.name,
        runtime_plan.odoo.name,
    }
    assert all(command[1:3] != ("network", "create") for command in ssh.commands)
    assert [command[1] for command in ssh.commands if command[0] == "docker"].count("run") == 1


def test_production_health_inspection_rejects_unhealthy_runtime() -> None:
    runtime_plan = plan()
    ssh = InspectingSsh(
        {
            runtime_plan.postgres.name: inspected(runtime_plan.postgres.name, runtime_plan.postgres.labels),
            runtime_plan.odoo.name: inspected(runtime_plan.odoo.name, runtime_plan.odoo.labels, healthy=False),
        }
    )
    mechanics = object.__new__(RemoteDockerMechanics)
    mechanics._ssh = cast(Any, ssh)

    assert mechanics.runtime_ready(InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container=runtime_plan.postgres.name, odoo_container=runtime_plan.odoo.name)) is False


def _live_entry(
    name: str,
    kind: str,
    operation: DurableOperationIdentity,
    live_id: str,
    *,
    creator_token: str | None = None,
) -> dict[str, Any]:
    labels = {
        "com.odoo-forge.operation": operation.operation_id,
        "com.odoo-forge.creator-token": creator_token or vps_provider._creator_token(operation, kind, name),
    }
    if kind == "volume":
        return {"Name": name, "Labels": labels}
    entry = inspected(name, labels)
    entry["Id"] = live_id
    return entry


@pytest.mark.parametrize(
    "live_id,creator_token",
    [("wrong-live-id", None), ("container-id", "wrong-creator-token")],
)
def test_compensation_refuses_replaced_created_resource_before_deletion(
    live_id: str, creator_token: str | None
) -> None:
    operation = DurableOperationIdentity(operation_id="unit7", request_digest="digest")
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({"managed-container": _live_entry("managed-container", "container", operation, live_id, creator_token=creator_token)})
    mechanics._ssh = cast(Any, ssh)
    record = vps_provider._owned(operation, "container", "managed-container", live_id="container-id")

    mechanics.destroy(InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo"), (record,))

    assert not any(command[:3] == ("docker", "rm", "-f") for command in ssh.commands)


@pytest.mark.parametrize(
    "kind,identifier,live_id,expected_prefix",
    [
        ("container", "managed-container", "container-id", ("docker", "rm", "-f")),
        ("network", "managed-network", "network-id", ("docker", "network", "rm")),
        ("volume", "managed-volume", "managed-volume", ("docker", "volume", "rm")),
    ],
)
def test_compensation_dispatches_deletion_by_resource_kind(
    kind: str, identifier: str, live_id: str, expected_prefix: tuple[str, ...]
) -> None:
    operation = DurableOperationIdentity(operation_id="unit7-kind", request_digest="digest")
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({identifier: _live_entry(identifier, kind, operation, live_id)})
    mechanics._ssh = cast(Any, ssh)
    record = vps_provider._owned(operation, kind, identifier, live_id=live_id)

    mechanics.destroy(InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo"), (record,))

    assert any(command[:3] == expected_prefix and command[-1] == live_id for command in ssh.commands)


def test_compensation_preserves_adopted_external_and_unknown_resources() -> None:
    mechanics = object.__new__(RemoteDockerMechanics)
    ssh = InspectingSsh({})
    mechanics._ssh = cast(Any, ssh)
    records = tuple(
        OwnershipRecord(
            ref=ResourceRef(identifier=identifier, resource_kind=kind, ownership=ownership),
            receipt=None,
        )
        for identifier, kind, ownership in (
            ("adopted", "container", ResourceOwnership.ADOPTED),
            ("external", "network", ResourceOwnership.EXTERNAL),
            ("unknown", "unknown", ResourceOwnership.CREATED),
        )
    )

    mechanics.destroy(InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo"), records)

    assert not any(command[0] == "docker" and command[1] in {"rm", "network", "volume"} and command[-1] in {"adopted", "external", "unknown"} for command in ssh.commands)

@dataclass
class Mechanics:
    calls: list[tuple[Any, ...]]
    unknown: bool = False
    http_ready: bool = True
    dns_ready: bool = True
    exposure_failure: bool = False
    exposure_ownership: ResourceOwnership = ResourceOwnership.CREATED
    destroyed: list[tuple[OwnershipRecord, ...]] | None = None

    def ensure_runtime(self, plan: BackendPlan, operation: DurableOperationIdentity) -> tuple[OwnershipRecord, ...]:
        self.calls.append(("run", plan.network.name))
        if self.unknown:
            raise Unknown("remote outcome unknown")
        return (owned(operation, "runtime", ResourceOwnership.CREATED),)

    def discover_runtime(self, ref: InstanceRef) -> tuple[OwnershipRecord, ...]:
        self.calls.append(("discover", ref.network))
        return ()

    def runtime_ready(self, ref: InstanceRef) -> bool:
        self.calls.append(("ready", ref.network))
        return True

    def ensure_http(self, ref: InstanceRef, hostname: str, operation: DurableOperationIdentity) -> OwnershipRecord:
        self.calls.append(("http", hostname))
        return owned(operation, "route", self.exposure_ownership)

    def verify_http(self, hostname: str) -> bool:
        self.calls.append(("http-ready", hostname))
        if self.exposure_failure:
            raise RuntimeError("exposure verification failed")
        return self.http_ready

    def verify_dns(self, hostname: str, target: str) -> bool:
        self.calls.append(("dns", hostname, target))
        return self.dns_ready

    def stop(self, ref: InstanceRef) -> None:
        self.calls.append(("stop", ref.network))
        if self.unknown:
            raise Unknown("remote outcome unknown")

    def destroy(self, ref: InstanceRef, ownership: tuple[OwnershipRecord, ...]) -> None:
        self.calls.append(("destroy", ref.network))
        if self.destroyed is not None:
            self.destroyed.append(ownership)
        if self.unknown:
            raise Unknown("remote outcome unknown")


class ReplayMechanics(Mechanics):
    def __init__(self, calls: list[tuple[Any, ...]]) -> None:
        super().__init__(calls)
        self.realized: tuple[OwnershipRecord, ...] = ()

    def ensure_runtime(
        self, plan: BackendPlan, operation: DurableOperationIdentity
    ) -> tuple[OwnershipRecord, ...]:
        self.calls.append(("ensure", plan.network.name))
        identifiers = (
            plan.network.name,
            *(volume.name for volume in plan.volumes),
            plan.postgres.name,
            plan.odoo.name,
        )
        kinds = ("network", *("volume" for _ in plan.volumes), "container", "container")
        self.realized = tuple(
            vps_provider._owned(operation, kind, identifier)
            for kind, identifier in zip(kinds, identifiers, strict=True)
        )
        return self.realized


def scope(project: str = "alpha") -> ProjectScope:
    return ProjectScope(tenant=TenantId(value="tenant"), project_id=project)


def owned(operation: DurableOperationIdentity, identifier: str, ownership: ResourceOwnership) -> OwnershipRecord:
    return OwnershipRecord(ref=ResourceRef(identifier=identifier, resource_kind="vps", ownership=ownership), receipt=OwnershipReceipt(operation=operation, owned_resource_ids=(identifier,)) if ownership is ResourceOwnership.CREATED else None)


def plan(project: str = "alpha") -> BackendPlan:
    labels = {"com.odoo-forge.project": project, "com.odoo-forge.instance": "one"}
    network = NetworkSpec(name=f"net-{project}", labels=labels)
    common: Any = {"network": network.name, "env": {}, "labels": labels, "volumes": []}
    return BackendPlan(network=network, volumes=[], postgres=ContainerSpec(name=f"{network.name}-db", image="postgres", role="postgres", **common), odoo=ContainerSpec(name=f"{network.name}-odoo", image="odoo", role="odoo", **common), postgres_credentials=CredentialHandle("pg"))


def provider(verb: str, mechanics: Mechanics | None = None) -> tuple[Any, Mechanics, Store]:
    mechanics, store = mechanics or Mechanics([]), Store()
    binding = VpsOperationBinding(scope=scope(), operation=DurableOperationIdentity(operation_id="op", request_digest="digest"), verb=verb, ownership=(), target=VpsTargetIdentity(host="vps.example.test", user="forge", port=22, host_key="key"), credential_handles=(CredentialHandle("pg"),))
    return bind_vps_operation(binding, store=cast(Any, store), mechanics=cast(Any, mechanics)), mechanics, store


def test_all_six_verbs_reject_a_wrong_bound_method_before_transport() -> None:
    for verb in ("run", "status", "stop", "destroy", "logs", "exec"):
        adapter, mechanics, _ = provider(verb)
        with pytest.raises(ValueError):
            adapter.status(InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo"))
        assert mechanics.calls == []


def test_scope_and_request_meaning_mismatch_are_rejected_before_transport() -> None:
    adapter, mechanics, _ = provider("run")
    with pytest.raises(ValueError):
        adapter.run(plan("other"))
    assert mechanics.calls == []


def test_same_operation_replays_without_duplicate_resources() -> None:
    adapter, mechanics, store = provider("run")
    operation = DurableOperationIdentity(operation_id="op", request_digest=adapter.request_digest(plan()))
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))
    ref = adapter.run(plan())
    calls = len(mechanics.calls)
    assert adapter.run(plan()) == ref and len(mechanics.calls) == calls
    assert store.records["op"].lifecycle is LifecycleState.SUCCEEDED


@pytest.mark.parametrize("volume_count", [0, 1])
def test_reconciliation_required_replay_realizes_missing_runtime_resources(volume_count: int) -> None:
    adapter, mechanics, store = provider("run", ReplayMechanics([]))
    replay_mechanics = cast(ReplayMechanics, mechanics)
    runtime_plan = plan().model_copy(
        update={
            "volumes": [
                VolumeSpec(name=f"runtime-volume-{volume_count}", labels={"role": "postgres"})
            ]
            if volume_count
            else []
        }
    )
    operation = DurableOperationIdentity(
        operation_id="interrupted-replay", request_digest=adapter.request_digest(runtime_plan)
    )
    adapter = bind_vps_operation(
        replace(adapter._binding, operation=operation),
        store=cast(Any, store),
        mechanics=cast(Any, mechanics),
    )
    record = store.create_or_load(operation)
    store.mark_reconciliation_required(operation.operation_id, record.revision)

    ref = adapter.run(runtime_plan)

    assert ref.network == runtime_plan.network.name
    assert [call[0] for call in mechanics.calls] == ["ensure", "ready"]
    expected_resources = {
        runtime_plan.network.name,
        runtime_plan.postgres.name,
        runtime_plan.odoo.name,
    }
    expected_resources.update(volume.name for volume in runtime_plan.volumes)
    assert {item.ref.identifier for item in replay_mechanics.realized} == expected_resources
    assert all(
        item.receipt is not None and item.receipt.operation == operation
        for item in replay_mechanics.realized
    )
    assert store.records[operation.operation_id].lifecycle is LifecycleState.SUCCEEDED
    assert adapter.run(runtime_plan) == ref
    assert [call[0] for call in mechanics.calls] == ["ensure", "ready"]


def test_http_dns_readiness_never_claims_tls() -> None:
    adapter, mechanics, store = provider("reconcile")
    ref = InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo")
    request = ExposureRequest(instance=ref, deployment=DeploymentSpec(pointer=InstancePointer(scope=scope(), instance_id=InstanceId(value="one")), resource=ResourceRef(identifier="net-alpha", resource_kind="instance", ownership=ResourceOwnership.CREATED), runtime=OdooRuntimeIntent(odoo_version="1"), exposure=ExposureIntent(hostname="odoo.example.test", protocol=RouteProtocol.HTTP, dns=RequirementPolicy.REQUIRED, tls=RequirementPolicy.DISABLED)), scope=scope(), operation=adapter._binding.operation)
    operation = DurableOperationIdentity(operation_id="op", request_digest=adapter.request_digest(request))
    request = request.model_copy(update={"operation": operation})
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))
    result = adapter.reconcile(request)
    assert result.outcome is ExposureOutcome.READY and result.ready is True and result.tls_ready is False
    assert result.routing_status is ExposureCheckStatus.VERIFIED and result.dns_status is ExposureCheckStatus.VERIFIED


@pytest.mark.parametrize("http_ready,dns_ready", [(False, True), (True, False)])
def test_pending_http_or_dns_readiness_is_not_durably_succeeded(
    http_ready: bool, dns_ready: bool
) -> None:
    adapter, mechanics, store = provider(
        "reconcile", Mechanics([], http_ready=http_ready, dns_ready=dns_ready)
    )
    ref = InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo")
    request = ExposureRequest(instance=ref, deployment=DeploymentSpec(pointer=InstancePointer(scope=scope(), instance_id=InstanceId(value="one")), resource=ResourceRef(identifier="net-alpha", resource_kind="instance", ownership=ResourceOwnership.CREATED), runtime=OdooRuntimeIntent(odoo_version="1"), exposure=ExposureIntent(hostname="odoo.example.test", protocol=RouteProtocol.HTTP, dns=RequirementPolicy.REQUIRED, tls=RequirementPolicy.DISABLED)), scope=scope(), operation=adapter._binding.operation)
    operation = DurableOperationIdentity(operation_id="op", request_digest=adapter.request_digest(request))
    request = request.model_copy(update={"operation": operation})
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    result = adapter.reconcile(request)

    assert result.outcome is ExposureOutcome.IN_PROGRESS
    assert result.ready is False
    assert store.records["op"].lifecycle is not LifecycleState.SUCCEEDED


@pytest.mark.parametrize("verb", ["stop", "destroy"])
def test_unknown_stop_and_destroy_are_durable_reconciliation_required(verb: str) -> None:
    adapter, mechanics, store = provider(verb, Mechanics([], unknown=True))
    ref = InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo")
    operation = DurableOperationIdentity(operation_id="op", request_digest=adapter.request_digest(ref))
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    with pytest.raises(Unknown):
        adapter.stop(ref) if verb == "stop" else adapter.destroy(ref)

    assert store.records["op"].lifecycle is LifecycleState.RECONCILIATION_REQUIRED


def test_unknown_mutation_is_durable_and_does_not_compensate_unverified_work() -> None:
    adapter, mechanics, store = provider("run", Mechanics([], unknown=True))
    operation = DurableOperationIdentity(operation_id="op", request_digest=adapter.request_digest(plan()))
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))
    with pytest.raises(Unknown):
        adapter.run(plan())
    assert store.records["op"].lifecycle is LifecycleState.RECONCILIATION_REQUIRED
    assert all("secret" not in str(item) for item in store.records["op"].recovery_evidence)


def test_terminal_commit_retains_verified_created_receipt_evidence() -> None:
    mechanics = Mechanics([])
    adapter, mechanics, store = provider("run", mechanics)
    runtime_plan = plan()
    operation = DurableOperationIdentity(operation_id="receipt-terminal", request_digest=adapter.request_digest(runtime_plan))
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    adapter.run(runtime_plan)

    terminal = store.records[operation.operation_id].terminal_commit
    assert terminal is not None
    assert any(
        evidence.event == "ownership_verified"
        and "runtime" in evidence.references
        for evidence in terminal.evidence
    )


def test_created_partial_exposure_is_compensated_after_later_failure() -> None:
    mechanics = Mechanics([], exposure_failure=True, destroyed=[])
    adapter, mechanics, store = provider("reconcile", mechanics)
    ref = InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo")
    request = ExposureRequest(instance=ref, deployment=DeploymentSpec(pointer=InstancePointer(scope=scope(), instance_id=InstanceId(value="one")), resource=ResourceRef(identifier="net-alpha", resource_kind="instance", ownership=ResourceOwnership.CREATED), runtime=OdooRuntimeIntent(odoo_version="1"), exposure=ExposureIntent(hostname="odoo.example.test", protocol=RouteProtocol.HTTP, dns=RequirementPolicy.REQUIRED, tls=RequirementPolicy.DISABLED)), scope=scope(), operation=adapter._binding.operation)
    operation = DurableOperationIdentity(operation_id="created-exposure-failure", request_digest="pending")
    request = request.model_copy(update={"operation": operation})
    operation = operation.model_copy(update={"request_digest": adapter.request_digest(request)})
    request = request.model_copy(update={"operation": operation})
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    with pytest.raises(RuntimeError, match="exposure verification"):
        adapter.reconcile(request)

    assert mechanics.destroyed == [
        (owned(operation, "route", ResourceOwnership.CREATED),)
    ]
    assert store.records[operation.operation_id].recovery_evidence


def test_adopted_partial_exposure_is_preserved_after_later_failure() -> None:
    mechanics = Mechanics([], exposure_failure=True, exposure_ownership=ResourceOwnership.ADOPTED, destroyed=[])
    adapter, mechanics, store = provider("reconcile", mechanics)
    ref = InstanceRef(project="alpha", instance="one", network="net-alpha", postgres_container="db", odoo_container="odoo")
    request = ExposureRequest(instance=ref, deployment=DeploymentSpec(pointer=InstancePointer(scope=scope(), instance_id=InstanceId(value="one")), resource=ResourceRef(identifier="net-alpha", resource_kind="instance", ownership=ResourceOwnership.ADOPTED), runtime=OdooRuntimeIntent(odoo_version="1"), exposure=ExposureIntent(hostname="odoo.example.test", protocol=RouteProtocol.HTTP, dns=RequirementPolicy.REQUIRED, tls=RequirementPolicy.DISABLED)), scope=scope(), operation=adapter._binding.operation)
    operation = DurableOperationIdentity(operation_id="adopted-exposure-failure", request_digest="pending")
    request = request.model_copy(update={"operation": operation})
    operation = operation.model_copy(update={"request_digest": adapter.request_digest(request)})
    request = request.model_copy(update={"operation": operation})
    adapter = bind_vps_operation(replace(adapter._binding, operation=operation), store=cast(Any, store), mechanics=cast(Any, mechanics))

    with pytest.raises(RuntimeError, match="exposure verification"):
        adapter.reconcile(request)

    assert mechanics.destroyed == []
