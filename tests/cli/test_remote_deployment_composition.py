from typing import Any, cast

from odoo_forge.backend.plan import BackendPlan
from odoo_forge.credentials.types import CredentialHandle, CredentialResolver
from odoo_forge.deployment_spec.types import DeploymentSpec
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.ports.durable_operation_store import DurableOperationStore
from odoo_forge.remote_deployment import (
    RemoteDeploymentCoordinator,
    RemoteTargetFingerprint,
)
from odoo_forge.resource_ownership.types import OwnershipRecord
from odoo_forge.tenancy.types import ProjectScope, TenantId
from odoo_forge_cli import _composition
from odoo_forge_docker.vps.provider import VpsMechanics, VpsOperationBinding, VpsTargetIdentity

SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
TARGET = VpsTargetIdentity(
    host="vps.example.test", user="deploy", port=22, host_key="ssh-ed25519 AAAA"
)
RUNTIME = DurableOperationIdentity(operation_id="run-1", request_digest="run-digest")
EXPOSURE = DurableOperationIdentity(operation_id="exposure-1", request_digest="exposure-digest")


def test_request_translation_keeps_provider_identity_out_of_core() -> None:
    request = _composition._make_remote_deployment_request(
        deployment=cast(DeploymentSpec, object()),
        plan=cast(BackendPlan, object()),
        target=TARGET,
        runtime_operation=RUNTIME,
        exposure_operation=EXPOSURE,
    )

    assert request.target == RemoteTargetFingerprint(
        host=TARGET.host, user=TARGET.user, port=TARGET.port, host_key=TARGET.host_key
    )
    assert request.target != cast(Any, "vps")


def test_coordinator_binds_run_and_reconcile_with_separate_operations(
    monkeypatch: Any,
) -> None:
    bindings: list[VpsOperationBinding] = []
    providers: list[object] = []
    store = cast(DurableOperationStore, object())
    mechanics = cast(VpsMechanics, object())
    resolver = cast(CredentialResolver, lambda _handle: "private-key")
    runtime_ownership = (cast(OwnershipRecord, object()),)

    def bind(
        binding: VpsOperationBinding,
        *,
        store: DurableOperationStore,
        mechanics: VpsMechanics | None = None,
        credentials: CredentialResolver | None = None,
    ) -> object:
        bindings.append(binding)
        assert store is not None and mechanics is not None and credentials is not None
        provider = object()
        providers.append(provider)
        return provider

    monkeypatch.setattr(_composition, "bind_vps_operation", bind)

    coordinator = _composition._make_remote_deployment_coordinator(
        scope=SCOPE,
        target=TARGET,
        runtime_operation=RUNTIME,
        runtime_credential_handles=(CredentialHandle("runtime"),),
        exposure_operation=EXPOSURE,
        exposure_credential_handles=(CredentialHandle("exposure"),),
        runtime_ownership=runtime_ownership,
        operation_store=store,
        mechanics=mechanics,
        credentials=resolver,
        recorder=lambda _receipt: None,
    )

    assert isinstance(coordinator, RemoteDeploymentCoordinator)
    assert len(bindings) == 2
    runtime_binding, exposure_binding = bindings
    assert runtime_binding.operation == RUNTIME
    assert runtime_binding.verb == "run"
    assert runtime_binding.ownership == runtime_ownership
    assert runtime_binding.target is TARGET
    assert runtime_binding.credential_handles == (CredentialHandle("runtime"),)
    assert exposure_binding.operation == EXPOSURE
    assert exposure_binding.verb == "reconcile"
    assert exposure_binding.ownership == ()
    assert exposure_binding.target is TARGET
    assert exposure_binding.credential_handles == (CredentialHandle("exposure"),)
    assert coordinator._runtime_provider is providers[0]
    assert coordinator._exposure_provider is providers[1]


def test_coordinator_omits_reconcile_binding_when_exposure_is_absent(
    monkeypatch: Any,
) -> None:
    bindings: list[VpsOperationBinding] = []

    def bind(binding: VpsOperationBinding, **_kwargs: Any) -> object:
        bindings.append(binding)
        return object()

    monkeypatch.setattr(_composition, "bind_vps_operation", bind)

    coordinator = _composition._make_remote_deployment_coordinator(
        scope=SCOPE,
        target=TARGET,
        runtime_operation=RUNTIME,
        runtime_credential_handles=(),
        operation_store=cast(DurableOperationStore, object()),
        mechanics=cast(VpsMechanics, object()),
        credentials=cast(CredentialResolver, lambda _handle: "private-key"),
        recorder=lambda _receipt: None,
    )

    assert len(bindings) == 1
    assert bindings[0].verb == "run"
    assert coordinator._exposure_provider is None
