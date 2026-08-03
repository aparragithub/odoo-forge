from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from odoo_forge.backend.status import InstanceStatus, RoleStatus
from odoo_forge.control_plane.models import (
    ReconciliationOutcome,
    ReconciliationResult,
    ReconciliationRow,
)
from odoo_forge.instance_registry import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.resource_ownership import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_server.app import create_app


def _record() -> InstanceRecord:
    scope = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
    return InstanceRecord(
        pointer=InstancePointer(scope=scope, instance_id=InstanceId(value="alpha")),
        resource=ResourceRef(
            identifier="odoo-forge-project-1-alpha",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def _status() -> InstanceStatus:
    healthy = RoleStatus(running=True, state="healthy", ready=True)
    return InstanceStatus(odoo=healthy, postgres=healthy)


class _FakeReconciler:
    def __init__(self, result: ReconciliationResult) -> None:
        self.result = result

    def list(self, scope: ProjectScope) -> ReconciliationResult:
        return self.result

    def get(self, pointer: InstancePointer) -> ReconciliationResult:
        return self.result


def _client(result: ReconciliationResult) -> TestClient:
    return TestClient(create_app(reconciler=_FakeReconciler(result)))


@pytest.mark.parametrize(
    "outcome",
    [
        ReconciliationOutcome.FRESH,
        ReconciliationOutcome.DRIFTED,
        ReconciliationOutcome.STALE_UNVERIFIED,
        ReconciliationOutcome.PARTIAL_FAILURE,
    ],
)
def test_list_returns_truthful_outcomes_with_200(outcome: ReconciliationOutcome) -> None:
    record = _record()
    result = ReconciliationResult(
        outcome=outcome,
        rows=(ReconciliationRow(record=record, live=_status(), outcome=outcome),),
    )
    response = _client(result).get("/api/v1/tenants/tenant-1/projects/project-1/instances")

    assert response.status_code == 200
    assert response.json()["outcome"] == outcome.value
    assert response.json()["rows"][0]["record"]["pointer"]["instance_id"]["value"] == "alpha"


def test_empty_list_is_200_but_empty_single_read_is_404() -> None:
    client = _client(ReconciliationResult(outcome=ReconciliationOutcome.EMPTY, rows=()))
    list_response = client.get("/api/v1/tenants/tenant-1/projects/project-1/instances")
    get_response = client.get("/api/v1/tenants/tenant-1/projects/project-1/instances/missing")

    assert list_response.status_code == 200
    assert list_response.json() == {"outcome": "empty", "rows": [], "detail": None}
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "instance not found"


def test_single_read_truthful_outcome_returns_200() -> None:
    record = _record()
    result = ReconciliationResult(
        outcome=ReconciliationOutcome.FRESH,
        rows=(ReconciliationRow(record=record, live=None, outcome=ReconciliationOutcome.FRESH),),
    )
    path = "/api/v1/tenants/tenant-1/projects/project-1/instances/alpha"
    response = _client(result).get(path)

    assert response.status_code == 200
    assert response.json()["outcome"] == "fresh"


def test_persistence_failure_is_503_and_redacted() -> None:
    result = ReconciliationResult(
        outcome=ReconciliationOutcome.PERSISTENCE_ERROR,
        rows=(),
        detail="instance registry could not be read",
    )
    response = _client(result).get("/api/v1/tenants/tenant-1/projects/project-1/instances")

    assert response.status_code == 503
    assert response.json() == {"detail": "instance registry unavailable"}


def test_schema_and_openapi_are_read_only() -> None:
    result = ReconciliationResult(outcome=ReconciliationOutcome.EMPTY, rows=())
    app = create_app(reconciler=_FakeReconciler(result))
    schema = app.openapi()
    response_schema = schema["components"]["schemas"]["ReconciliationResponse"]
    row_schema = schema["components"]["schemas"]["ReconciliationRowResponse"]

    assert set(response_schema["required"]) == {"outcome", "rows"}
    assert {"record", "live", "outcome"}.issubset(row_schema["required"])
    assert all(set(item) == {"get"} for item in schema["paths"].values())
