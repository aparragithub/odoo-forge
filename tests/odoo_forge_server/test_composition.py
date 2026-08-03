from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from odoo_forge.backend.status import InstanceRef, InstanceStatus, RoleStatus
from odoo_forge.provider_catalog import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderKind,
)
from odoo_forge_instances_postgres.adapter import Connection
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


def test_composition_rejects_unresolved_backend_catalog() -> None:
    empty = ProviderCatalog(approved_adapters=(), global_bindings=())

    try:
        create_production_app(database_url="postgresql://unused", provider_catalog=empty)
    except RuntimeError as error:
        assert "backend provider catalog resolution failed" in str(error)
    else:
        raise AssertionError("unresolved provider catalog must block composition")
