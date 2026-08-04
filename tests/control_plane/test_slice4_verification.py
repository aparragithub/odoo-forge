from __future__ import annotations

from fastapi.testclient import TestClient

from odoo_forge.backend.status import InstanceStatus, RoleStatus
from odoo_forge.control_plane.authority import ControlPlaneAuthority, RegistrationRequest
from odoo_forge.control_plane.models import ReconciliationOutcome
from odoo_forge.control_plane.reconcile import Reconciler
from odoo_forge.durable_operations import DurableOperationIdentity
from odoo_forge.instance_registry import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.ports.resource_custody import (
    CustodyRequest,
    CustodyStartingState,
    CustodyTransition,
    custody_request_digest,
)
from odoo_forge.resource_ownership import OwnershipReceipt, ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_instances_postgres.fakes import FakeInstanceRegistry
from odoo_forge_server.app import UiRuntime, create_app

_SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
_POINTER = InstancePointer(scope=_SCOPE, instance_id=InstanceId(value="alpha"))
_RESOURCE = ResourceRef(
    identifier="database-alpha",
    resource_kind="container",
    ownership=ResourceOwnership.CREATED,
)


class _Custody:
    def __init__(self) -> None:
        self.calls: list[CustodyRequest] = []

    def confirm(self, request: CustodyRequest) -> OwnershipReceipt:
        self.calls.append(request)
        return OwnershipReceipt(
            operation=request.operation,
            owned_resource_ids=(request.resource_id,),
            live_proof_expected=True,
        )


def _request() -> RegistrationRequest:
    operation_id = "postgres-docker:verification-op"
    digest = custody_request_digest(
        operation_id=operation_id,
        pointer=_POINTER,
        resource=_RESOURCE,
        resource_name=_RESOURCE.identifier,
        resource_id="immutable-alpha",
        starting_state=CustodyStartingState.UNRESERVED,
        requested_transition=CustodyTransition.RESERVE_BIND_ACTIVATE,
    )
    return RegistrationRequest(
        operation=DurableOperationIdentity(operation_id=operation_id, request_digest=digest),
        pointer=_POINTER,
        resource=_RESOURCE,
        resource_name=_RESOURCE.identifier,
        resource_id="immutable-alpha",
    )


def _healthy() -> InstanceStatus:
    role = RoleStatus(running=True, state="healthy", ready=True)
    return InstanceStatus(odoo=role, postgres=role)


def _client(registry: FakeInstanceRegistry) -> TestClient:
    reconciler = Reconciler(registry, lambda ref: _healthy())
    return TestClient(
        create_app(reconciler=reconciler, ui_runtime=UiRuntime("127.0.0.1")),
        base_url="http://127.0.0.1",
    )


def test_accepted_registration_appears_through_existing_reads() -> None:
    registry = FakeInstanceRegistry()
    custody = _Custody()
    accepted = ControlPlaneAuthority(custody, registry).register(_request())
    client = _client(registry)

    api = client.get("/api/v1/tenants/tenant-1/projects/project-1/instances/alpha")
    ui = client.get("/ui/tenants/tenant-1/projects/project-1/instances")

    assert api.status_code == 200
    assert api.json()["outcome"] == ReconciliationOutcome.STALE_UNVERIFIED.value
    assert api.json()["rows"][0]["record"] == accepted.model_dump(mode="json")
    assert ui.status_code == 200
    assert "alpha" in ui.text and "stale/unverified" in ui.text
    assert len(custody.calls) == 1


def test_existing_reads_are_no_write_and_remain_get_only() -> None:
    registry = FakeInstanceRegistry()
    custody = _Custody()
    authority = ControlPlaneAuthority(custody, registry)
    accepted = authority.register(_request())
    client = _client(registry)
    api_path = "/api/v1/tenants/tenant-1/projects/project-1/instances/alpha"
    ui_path = "/ui/tenants/tenant-1/projects/project-1/instances/alpha"

    assert client.get(api_path).status_code == 200
    assert client.get(ui_path).status_code == 200
    assert registry.get(_POINTER) == accepted
    assert registry.list(_SCOPE) == (accepted,)
    assert len(custody.calls) == 1
    for method in (client.post, client.put, client.patch, client.delete):
        assert method(api_path).status_code == 405
        assert method(ui_path).status_code == 405


def test_legacy_nullable_record_survives_read_only_rollback_boundary() -> None:
    legacy = InstanceRecord(pointer=_POINTER, resource=_RESOURCE)
    registry = FakeInstanceRegistry()
    registry.store(legacy)
    client = _client(registry)

    api = client.get("/api/v1/tenants/tenant-1/projects/project-1/instances/alpha")
    ui = client.get("/ui/tenants/tenant-1/projects/project-1/instances")

    assert api.status_code == 200
    assert api.json()["rows"][0]["record"]["receipt"] is None
    assert ui.status_code == 200 and "alpha" in ui.text
    assert registry.get(_POINTER) == legacy
