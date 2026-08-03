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


def _record(
    *, tenant: str = "tenant-1", project: str = "project-1", instance: str = "alpha"
) -> InstanceRecord:
    scope = ProjectScope(tenant=TenantId(value=tenant), project_id=project)
    return InstanceRecord(
        pointer=InstancePointer(scope=scope, instance_id=InstanceId(value=instance)),
        resource=ResourceRef(
            identifier=f"odoo-forge-{project}-{instance}",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def _status() -> InstanceStatus:
    healthy = RoleStatus(running=True, state="healthy", ready=True)
    return InstanceStatus(odoo=healthy, postgres=healthy)


class _FakeReconciler:
    def __init__(
        self, result: ReconciliationResult | dict[tuple[str, str, str], ReconciliationResult]
    ) -> None:
        if isinstance(result, ReconciliationResult):
            self.results = dict.fromkeys(
                (
                    ("tenant-1", "project-1", ""),
                    ("tenant-1", "project-1", "alpha"),
                    ("tenant-1", "project-1", "missing"),
                ),
                result,
            )
        else:
            self.results = result

    def list(self, scope: ProjectScope) -> ReconciliationResult:
        return self.results[(scope.tenant.value, scope.project_id, "")]

    def get(self, pointer: InstancePointer) -> ReconciliationResult:
        return self.results[
            (pointer.scope.tenant.value, pointer.scope.project_id, pointer.instance_id.value)
        ]


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


def _result(record: InstanceRecord) -> ReconciliationResult:
    return ReconciliationResult(
        outcome=ReconciliationOutcome.FRESH,
        rows=(
            ReconciliationRow(record=record, live=_status(), outcome=ReconciliationOutcome.FRESH),
        ),
    )


def test_list_scopes_return_only_their_matching_records() -> None:
    first = _record(tenant="tenant-1", project="project-1", instance="alpha")
    second = _record(tenant="tenant-2", project="project-2", instance="beta")
    first_result, second_result = _result(first), _result(second)
    client = TestClient(
        create_app(
            reconciler=_FakeReconciler(
                {
                    ("tenant-1", "project-1", ""): first_result,
                    ("tenant-2", "project-2", ""): second_result,
                },
            )
        )
    )

    first_response = client.get("/api/v1/tenants/tenant-1/projects/project-1/instances")
    second_response = client.get("/api/v1/tenants/tenant-2/projects/project-2/instances")

    assert [row["record"] for row in first_response.json()["rows"]] == [
        first.model_dump(mode="json")
    ]
    assert [row["record"] for row in second_response.json()["rows"]] == [
        second.model_dump(mode="json")
    ]


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
