from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from odoo_forge.backend.status import InstanceRef, InstanceStatus, RoleStatus
from odoo_forge.control_plane.authority import ControlPlaneAuthority
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.provider_catalog import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderKind,
)
from odoo_forge.resource_ownership import OwnershipReceipt
from odoo_forge_instances_postgres.adapter import Connection
from odoo_forge_server.app import UiRuntime
from odoo_forge_server.composition import create_production_app


class _Backend:
    def __init__(self) -> None:
        self.status_calls: list[InstanceRef] = []

    def status(self, ref: InstanceRef) -> InstanceStatus:
        self.status_calls.append(ref)
        return InstanceStatus(
            odoo=RoleStatus(running=True, state="healthy", ready=True),
            postgres=RoleStatus(running=True, state="no_healthcheck", ready=True),
        )


class _Cursor:
    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        pass

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        return [
            (
                "tenant-1",
                "project-1",
                "alpha",
                "odoo-forge-project-1-alpha",
                "instance",
                "created",
            )
        ]


class _Connection:
    def cursor(self) -> _Cursor:
        return _Cursor()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _connection() -> Iterator[Connection]:
    yield _Connection()


def _catalog() -> ProviderCatalog:
    return ProviderCatalog(
        approved_adapters=(ApprovedProviderAdapter(ProviderKind.BACKEND, "docker"),),
        global_bindings=(GlobalProviderBinding(ProviderKind.BACKEND, "docker"),),
    )


def test_composition_resolves_catalog_and_runs_status_through_registry() -> None:
    backend, acquired = _Backend(), []

    def acquire() -> AbstractContextManager[Connection]:
        acquired.append(True)
        return contextmanager(_connection)()

    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": backend},
        acquire_connection=acquire,
    )

    assert isinstance(app, FastAPI)
    assert acquired == []
    response = TestClient(app).get("/api/v1/tenants/tenant-1/projects/project-1/instances")
    assert response.status_code == 200
    assert response.json()["outcome"] == "fresh"
    assert response.json()["rows"][0]["live"]["postgres"] == {
        "running": True,
        "state": "no_healthcheck",
        "ready": True,
    }


def test_composition_injects_the_same_reconciler_into_the_ui() -> None:
    backend = _Backend()
    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": backend},
        acquire_connection=lambda: contextmanager(_connection)(),
        ui_runtime=UiRuntime("127.0.0.1"),
    )
    client = TestClient(app, base_url="http://127.0.0.1")
    api = client.get("/api/v1/tenants/tenant-1/projects/project-1/instances")
    ui = client.get("/ui/tenants/tenant-1/projects/project-1/instances")

    assert api.status_code == ui.status_code == 200
    assert api.json()["outcome"] == "fresh"
    assert "Aggregate outcome: <strong>fresh</strong>" in ui.text
    assert [ref.network for ref in backend.status_calls] == [
        "odoo-forge-project-1-alpha",
        "odoo-forge-project-1-alpha",
    ]


class _FakeCustody:
    def __init__(self) -> None:
        self.calls = 0

    def confirm(self, request: object) -> OwnershipReceipt:
        self.calls += 1
        return OwnershipReceipt(
            operation=DurableOperationIdentity(
                operation_id="postgres-docker:op-1", request_digest="a" * 64
            ),
            owned_resource_ids=("container-1",),
        )


def test_composition_wires_one_authority_over_the_same_registry_with_no_new_route() -> None:
    custody = _FakeCustody()
    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
        custody_adapter=custody,
    )

    authority = app.state.control_plane_authority
    assert isinstance(authority, ControlPlaneAuthority)
    assert authority._registry is app.state.registry

    methods = [route.methods for route in app.routes if hasattr(route, "methods")]
    assert all(methods_set <= {"GET", "HEAD"} for methods_set in methods)


def test_composition_rejects_unresolved_backend_catalog() -> None:
    empty = ProviderCatalog(approved_adapters=(), global_bindings=())

    try:
        create_production_app(database_url="postgresql://unused", provider_catalog=empty)
    except RuntimeError as error:
        assert "backend provider catalog resolution failed" in str(error)
    else:
        raise AssertionError("unresolved provider catalog must block composition")
