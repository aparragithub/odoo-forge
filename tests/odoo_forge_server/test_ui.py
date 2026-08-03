from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
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
from odoo_forge_server.app import UiRuntime, create_app


def _record(instance: str = "alpha") -> InstanceRecord:
    scope = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
    return InstanceRecord(
        pointer=InstancePointer(scope=scope, instance_id=InstanceId(value=instance)),
        resource=ResourceRef(
            identifier=f"odoo-forge-project-1-{instance}",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def _status(*, ready: bool = True) -> InstanceStatus:
    role = RoleStatus(running=True, state="healthy" if ready else "starting", ready=ready)
    return InstanceStatus(odoo=role, postgres=role)


def _result(
    outcome: ReconciliationOutcome, *, live: InstanceStatus | None = None
) -> ReconciliationResult:
    if outcome in (ReconciliationOutcome.EMPTY, ReconciliationOutcome.PERSISTENCE_ERROR):
        return ReconciliationResult(outcome=outcome, rows=(), detail="secret database detail")
    return ReconciliationResult(
        outcome=outcome,
        rows=(
            ReconciliationRow(
                record=_record(), live=live, outcome=outcome, detail="row diagnostic"
            ),
        ),
    )


class _FakeReconciler:
    def __init__(self, results: tuple[ReconciliationResult, ...]) -> None:
        self.results = iter(results)
        self.list_calls = 0

    def list(self, scope: ProjectScope) -> ReconciliationResult:
        self.list_calls += 1
        return next(self.results)

    def get(self, pointer: InstancePointer) -> ReconciliationResult:
        return next(self.results)


def _client(*results: ReconciliationResult) -> tuple[TestClient, _FakeReconciler]:
    reconciler = _FakeReconciler(results)
    return TestClient(
        create_app(reconciler=reconciler, ui_runtime=UiRuntime("127.0.0.1")),
        base_url="http://127.0.0.1",
    ), reconciler


@pytest.mark.parametrize("host", ["localhost", "0.0.0.0", "192.168.1.20", "not-an-ip"])
def test_ui_runtime_rejects_production_and_non_loopback_hosts(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        UiRuntime(host)
    with pytest.raises(ValueError, match="production"):
        UiRuntime("127.0.0.1", production=True)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_ui_runtime_accepts_literal_loopback_ips(host: str) -> None:
    assert UiRuntime(host).bind_host == host


def test_ui_rejects_request_on_a_different_server_address() -> None:
    client, _ = _client(_result(ReconciliationOutcome.EMPTY))
    public_client = TestClient(client.app, base_url="http://127.0.0.2")
    response = public_client.get("/ui/tenants/tenant-1/projects/project-1/instances")
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("outcome", "label"),
    [
        (ReconciliationOutcome.FRESH, "fresh"),
        (ReconciliationOutcome.DRIFTED, "drifted"),
        (ReconciliationOutcome.STALE_UNVERIFIED, "stale/unverified"),
        (ReconciliationOutcome.PARTIAL_FAILURE, "partial-failure"),
    ],
)
def test_dashboard_renders_truthful_outcome_and_docker_observation(
    outcome: ReconciliationOutcome, label: str
) -> None:
    client, reconciler = _client(
        _result(outcome, live=_status(ready=outcome is not ReconciliationOutcome.STALE_UNVERIFIED))
    )
    response = client.get("/ui/tenants/tenant-1/projects/project-1/instances")
    assert response.status_code == 200
    assert label in response.text
    assert "Docker observed" in response.text
    assert reconciler.list_calls == 1


@pytest.mark.parametrize(
    ("outcome", "status"),
    [(ReconciliationOutcome.EMPTY, 200), (ReconciliationOutcome.PERSISTENCE_ERROR, 503)],
)
def test_dashboard_preserves_empty_and_redacts_persistence_error(
    outcome: ReconciliationOutcome, status: int
) -> None:
    client, _ = _client(_result(outcome))
    response = client.get("/ui/tenants/tenant-1/projects/project-1/instances")
    assert response.status_code == status
    assert outcome.value.replace("_", "-") in response.text
    assert "secret database detail" not in response.text
    if outcome is ReconciliationOutcome.PERSISTENCE_ERROR:
        detail = _client(_result(outcome))[0].get(
            "/ui/tenants/tenant-1/projects/project-1/instances/alpha"
        )
        assert detail.status_code == 503 and "secret database detail" not in detail.text


@pytest.mark.parametrize(
    "path",
    [
        "/ui/tenants/tenant-1/projects/project-1/instances",
        "/ui/tenants/tenant-1/projects/project-1/instances/alpha",
    ],
)
def test_drift_views_show_expected_and_observed_difference(path: str) -> None:
    client, _ = _client(_result(ReconciliationOutcome.DRIFTED, live=_status(ready=False)))
    response = client.get(path)
    assert response.status_code == 200
    assert "Configured/expected" in response.text
    assert "Odoo running=True, state=healthy, ready=True" in response.text
    assert "Expected-versus-Docker-observed difference" in response.text
    assert "Odoo state expected=healthy, observed=starting" in response.text
    assert "Odoo ready expected=True, observed=False" in response.text


def test_detail_renders_drift_diagnostics_and_unknown_is_bounded() -> None:
    client, _ = _client(_result(ReconciliationOutcome.DRIFTED, live=_status(ready=False)))
    response = client.get("/ui/tenants/tenant-1/projects/project-1/instances/alpha")
    assert response.status_code == 200
    assert "drifted" in response.text and "row diagnostic" in response.text
    missing, _ = _client(_result(ReconciliationOutcome.EMPTY))
    assert (
        missing.get("/ui/tenants/tenant-1/projects/project-1/instances/missing").status_code == 404
    )


def test_polling_reconciles_again_and_ui_is_get_only() -> None:
    client, reconciler = _client(
        _result(ReconciliationOutcome.FRESH, live=_status()),
        _result(ReconciliationOutcome.DRIFTED, live=_status(ready=False)),
    )
    path = "/ui/tenants/tenant-1/projects/project-1/instances"
    first, second = client.get(path), client.get(path)
    assert "fresh" in first.text and "drifted" in second.text
    assert reconciler.list_calls == 2
    assert client.post(path).status_code == 405
    assert all(
        route.methods <= {"GET", "HEAD", "OPTIONS"}
        for route in cast(FastAPI, client.app).routes
        if isinstance(route, APIRoute) and route.path.startswith("/ui/")
    )
