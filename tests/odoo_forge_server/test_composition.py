from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from odoo_forge.backend.status import InstanceRef, InstanceStatus, RoleStatus
from odoo_forge.control_plane.authority import ControlPlaneAuthority, RegistrationRequest
from odoo_forge.database.types import DatabaseRef
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.errors import InstanceRecordNotFoundError
from odoo_forge.instance_registry.types import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.ports.resource_custody import (
    CustodyStartingState,
    CustodyTransition,
    custody_request_digest,
)
from odoo_forge.provider_catalog import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderKind,
)
from odoo_forge.resource_lifecycle.service import LifecycleService
from odoo_forge.resource_lifecycle.types import (
    LifecycleAuthorization,
    LifecycleEvidence,
    LifecycleJournalEvent,
    LifecycleOutcome,
    LifecyclePolicy,
    QuarantineHistory,
    ResourceClass,
)
from odoo_forge.resource_ownership import OwnershipReceipt
from odoo_forge.resource_ownership.types import ResourceOwnership, ResourceRef
from odoo_forge.tenancy.types import ProjectScope, TenantId
from odoo_forge_instances_postgres.adapter import Connection
from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority
from odoo_forge_postgres_docker.lifecycle import (
    JsonlLifecycleJournal,
    PostgresDockerLifecycleAdapter,
)
from odoo_forge_server.app import UiRuntime
from odoo_forge_server.composition import EnvLifecycleSchedulerGate, create_production_app


class _Backend:
    def __init__(self) -> None:
        self.status_calls: list[InstanceRef] = []

    def status(self, ref: InstanceRef) -> InstanceStatus:
        self.status_calls.append(ref)
        return InstanceStatus(
            odoo=RoleStatus(running=True, state="healthy", ready=True),
            postgres=RoleStatus(running=True, state="no_healthcheck", ready=True),
        )


_LIST_ROW = (
    "tenant-1",
    "project-1",
    "alpha",
    "odoo-forge-project-1-alpha",
    "instance",
    "created",
)
_REGISTERED_ROW = (
    "tenant-1",
    "project-1",
    "alpha",
    "odoo-forge-project-1-alpha",
    "container",
    "created",
    "postgres-docker:op-1",
    "a" * 64,
    ["container-1"],
    True,
)
_ENVIRONMENT_ROW = (
    "qa",
    "platform",
    "tenant-1",
    "project-1",
    "active",
    "policy-qa",
    [{"source_environment_id": "production", "target_environment_id": "qa"}],
)
_GRANT_ROW = (
    "refresh-42",
    "qa",
    "operator-1",
    datetime(2030, 1, 1, tzinfo=UTC),
    "approved refresh",
    "audit-42",
)
_REGISTERED_POINTER = InstancePointer(
    scope=ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1"),
    instance_id=InstanceId(value="alpha"),
)
_REGISTERED_RESOURCE = ResourceRef(
    identifier="odoo-forge-project-1-alpha",
    resource_kind="container",
    ownership=ResourceOwnership.CREATED,
)


def _registration_request() -> RegistrationRequest:
    operation = "postgres-docker:op-1"
    return RegistrationRequest(
        operation=DurableOperationIdentity(
            operation_id=operation,
            request_digest=custody_request_digest(
                operation_id=operation,
                pointer=_REGISTERED_POINTER,
                resource=_REGISTERED_RESOURCE,
                resource_name=_REGISTERED_RESOURCE.identifier,
                resource_id="container-1",
                starting_state=CustodyStartingState.UNRESERVED,
                requested_transition=CustodyTransition.RESERVE_BIND_ACTIVATE,
            ),
        ),
        pointer=_REGISTERED_POINTER,
        resource=_REGISTERED_RESOURCE,
        resource_name=_REGISTERED_RESOURCE.identifier,
        resource_id="container-1",
    )


class _Cursor:
    """Answer by statement so a register round-trip can be observed.

    The registry issues a lookup that must find nothing, then an insert that
    must return the committed row, so a single fixed response cannot serve
    both.
    """

    def __init__(self) -> None:
        self._inserting = False
        self._register_lookup = False
        self._authority_row: tuple[object, ...] | None = None

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        normalized = " ".join(query.split()).upper()
        self._inserting = normalized.startswith("INSERT")
        self._register_lookup = "OPERATION_ID = " in normalized
        if "FROM PUBLIC.DATA_ENVIRONMENT_REGISTRY" in normalized:
            self._authority_row = _ENVIRONMENT_ROW
        elif "FROM PUBLIC.RAW_DATA_GRANTS" in normalized:
            self._authority_row = _GRANT_ROW

    def fetchone(self) -> tuple[object, ...] | None:
        return _REGISTERED_ROW if self._inserting else self._authority_row

    def fetchall(self) -> list[tuple[object, ...]]:
        if self._inserting or self._register_lookup:
            return []
        return [_LIST_ROW]


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


def test_composition_forwards_manifest_seam_to_api_and_ssr_as_get_only() -> None:
    locations: list[Path] = []

    def load_manifest(path: Path) -> object:
        locations.append(path)
        return {
            "name": "safe-project",
            "odoo_version": "19.0",
            "edition": "community",
            "layers": [],
            "client": {"addons_path": "/secret/client"},
        }

    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
        ui_runtime=UiRuntime("127.0.0.1"),
        manifest_scope=_REGISTERED_POINTER.scope,
        manifest_location=Path("/secret/project.yaml"),
        manifest_loader=load_manifest,
    )
    client = TestClient(app, base_url="http://127.0.0.1")
    api = client.get("/api/v1/tenants/tenant-1/projects/project-1/manifest")
    ui = client.get("/ui/tenants/tenant-1/projects/project-1/instances")

    assert api.status_code == 200 and api.json()["summary"]["project_name"] == "safe-project"
    assert ui.status_code == 200 and "safe-project" in ui.text
    assert locations == [Path("/secret/project.yaml"), Path("/secret/project.yaml")]
    manifest_path = "/api/v1/tenants/{tenant_id}/projects/{project_id}/manifest"
    assert set(app.openapi()["paths"][manifest_path]) == {"get"}
    assert client.head(  # noqa: E501
        manifest_path.replace("{tenant_id}", "tenant-1").replace("{project_id}", "project-1")
    ).status_code == 405


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


def test_composition_wires_one_authority_over_the_app_registry_with_no_new_route() -> None:
    """Assert the wiring through behavior, not through private attributes.

    Registering via the authority must reach the app's own connection factory
    and must go through the INJECTED custody adapter; a default Docker adapter
    would never touch this fake.
    """
    custody, acquired = _FakeCustody(), []

    def acquire() -> AbstractContextManager[Connection]:
        acquired.append(True)
        return contextmanager(_connection)()

    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=acquire,
        custody_adapter=custody,
    )

    authority = app.state.control_plane_authority
    assert isinstance(authority, ControlPlaneAuthority)
    assert acquired == []

    registered = authority.register(_registration_request())

    assert custody.calls == 1
    assert acquired, "the authority must register through the app's connection factory"
    assert registered.pointer == _registration_request().pointer
    assert registered.receipt is not None

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


def test_composition_exposes_bounded_data_environment_adapters_and_service() -> None:
    from odoo_forge.data_environments.service import DataEnvironmentService

    service, acquired = object.__new__(DataEnvironmentService), []

    def acquire() -> AbstractContextManager[Connection]:
        acquired.append(True)
        return contextmanager(_connection)()

    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        acquire_connection=acquire,
        data_environment_service=service,
    )

    assert app.state.data_environment_service is service
    assert app.state.data_environment_registry.resolve("qa").environment_id == "qa"
    assert (
        app.state.raw_data_grant_authority.authorize("refresh-42", "qa").audit_reference
        == "audit-42"
    )
    assert acquired == [True, True]
    assert all(
        route.methods <= {"GET", "HEAD"} for route in app.routes if hasattr(route, "methods")
    )


LIFECYCLE_SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
LIFECYCLE_POLICY = LifecyclePolicy(ttl=timedelta(days=7), grace=timedelta(days=1))
LIFECYCLE_AUTHORIZATION = LifecycleAuthorization(actor="operator-1", reason="approved recovery")
LIFECYCLE_NOW = datetime(2026, 1, 10, tzinfo=UTC)


class _EmptyRegistry:
    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        return ()

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        raise InstanceRecordNotFoundError(pointer)


class _OneRecordRegistry:
    def __init__(self, record: InstanceRecord) -> None:
        self._record = record

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        return (self._record,)

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        if pointer == self._record.pointer:
            return self._record
        raise InstanceRecordNotFoundError(pointer)


_INSPECT_TEMPLATE = (
    '[{{"Id":"docker-1","Config":{{"Labels":{{"io.odoo-forge.operation":"op-1",'
    '"io.odoo-forge.resource-class":"{resource_class}","io.odoo-forge.last-activity":'
    '"2020-01-01T00:00:00+00:00","io.odoo-forge.evidence-digest":"digest-1"}}}},'
    '"State":{{"Dead":false}}}}]'
)


def _docker_runner(resource_class: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[1:3] == ["ps", "-a"]:
            return subprocess.CompletedProcess(argv, 0, "docker-1\n", "")
        return subprocess.CompletedProcess(
            argv, 0, _INSPECT_TEMPLATE.format(resource_class=resource_class), ""
        )

    return run


def _live_authority(tmp_path: Path, resource_class: str) -> LocalOwnershipAuthority:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(
        {
            "operation": "op-1",
            "kind": "container",
            "name": "database-1",
            "docker_id": "docker-1",
            "state": "active",
            "tenant_id": LIFECYCLE_SCOPE.tenant.value,
            "project_id": LIFECYCLE_SCOPE.project_id,
            "request_digest": "request-1",
            "resource_class": resource_class,
            "last_activity": "2020-01-01T00:00:00+00:00",
            "evidence_digest": "digest-1",
        }
    )
    return authority


def _composed_lifecycle_service(
    *, tmp_path: Path, registry: _EmptyRegistry | _OneRecordRegistry, resource_class: str
) -> tuple[LifecycleService, Mock]:
    provider = Mock()
    gateway = PostgresDockerLifecycleAdapter(
        provider=provider,
        authority=_live_authority(tmp_path, resource_class),
        runner=_docker_runner(resource_class),
    )
    journal = JsonlLifecycleJournal(tmp_path / "lifecycle.jsonl")
    return (
        LifecycleService(
            registry=cast(InstanceRegistry, registry), gateway=gateway, journal=journal
        ),
        provider,
    )


def test_composition_shares_the_same_registry_and_authority_with_lifecycle_service() -> None:
    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
    )

    assert app.state.lifecycle_service.registry is app.state.registry
    assert app.state.lifecycle_service.gateway.authority is app.state.resource_authority
    assert isinstance(app.state.lifecycle_service.journal, JsonlLifecycleJournal)
    assert all(
        route.methods <= {"GET", "HEAD"} for route in app.routes if hasattr(route, "methods")
    )


def test_composition_lifecycle_scheduler_gate_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ODOO_FORGE_LIFECYCLE_SCHEDULER_ENABLED", raising=False)

    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
    )

    assert isinstance(app.state.lifecycle_scheduler_gate, EnvLifecycleSchedulerGate)
    assert app.state.lifecycle_scheduler_gate.enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "yes", "0", ""])
def test_composition_lifecycle_scheduler_gate_rejects_inexact_opt_in_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ODOO_FORGE_LIFECYCLE_SCHEDULER_ENABLED", value)

    assert EnvLifecycleSchedulerGate().enabled() is False


def test_composition_lifecycle_scheduler_gate_opts_in_on_exact_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODOO_FORGE_LIFECYCLE_SCHEDULER_ENABLED", "1")

    assert EnvLifecycleSchedulerGate().enabled() is True


def test_composition_lifecycle_service_reports_only_for_prod_resources_with_zero_mutation(
    tmp_path: Path,
) -> None:
    service, provider = _composed_lifecycle_service(
        tmp_path=tmp_path, registry=_EmptyRegistry(), resource_class="prod"
    )
    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
        lifecycle_service=service,
    )

    results = app.state.lifecycle_service.run(
        LIFECYCLE_SCOPE, LIFECYCLE_POLICY, LIFECYCLE_AUTHORIZATION, now=LIFECYCLE_NOW
    )

    assert [result.outcome for result in results] == [LifecycleOutcome.HUMAN_INTERVENTION]
    assert provider.mock_calls == []


def test_composition_lifecycle_service_detects_lineage_contradiction_with_zero_mutation(
    tmp_path: Path,
) -> None:
    pointer = InstancePointer(scope=LIFECYCLE_SCOPE, instance_id=InstanceId(value="database-1"))
    record = InstanceRecord(
        pointer=pointer,
        resource=ResourceRef(
            identifier="database-1", resource_kind="database", ownership=ResourceOwnership.CREATED
        ),
        receipt=OwnershipReceipt(
            operation=DurableOperationIdentity(operation_id="other-op", request_digest="d" * 64),
            owned_resource_ids=("database-1",),
        ),
    )
    service, provider = _composed_lifecycle_service(
        tmp_path=tmp_path, registry=_OneRecordRegistry(record), resource_class="dev"
    )
    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
        lifecycle_service=service,
    )

    results = app.state.lifecycle_service.run(
        LIFECYCLE_SCOPE, LIFECYCLE_POLICY, LIFECYCLE_AUTHORIZATION, now=LIFECYCLE_NOW
    )

    assert [result.outcome for result in results] == [LifecycleOutcome.HUMAN_INTERVENTION]
    assert provider.mock_calls == []


def test_composition_lifecycle_service_confirms_zombie_quarantine_through_composed_journal(
    tmp_path: Path,
) -> None:
    provider = Mock()
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(
        {
            "operation": "op-0",
            "kind": "container",
            "name": "retired-1",
            "docker_id": "docker-0",
            "state": "retired",
        }
    )
    history = QuarantineHistory(
        pointer=InstancePointer(scope=LIFECYCLE_SCOPE, instance_id=InstanceId(value="database-1")),
        scope=LIFECYCLE_SCOPE,
        resource=DatabaseRef(identifier="database-1", ownership=ResourceOwnership.CREATED),
        operation=DurableOperationIdentity(operation_id="op-1", request_digest="d" * 64),
        evidence_digest="digest-1",
        resource_class=ResourceClass.DEV,
        quarantined_at=LIFECYCLE_NOW - timedelta(days=3),
    )
    journal_path = tmp_path / "lifecycle.jsonl"
    JsonlLifecycleJournal(journal_path).append(
        LifecycleJournalEvent(
            policy=LIFECYCLE_POLICY,
            evidence=LifecycleEvidence(source="lifecycle", digest="digest-1"),
            authorization=LIFECYCLE_AUTHORIZATION,
            outcome=LifecycleOutcome.QUARANTINED,
            history=history,
        )
    )
    provider.quarantine.return_value = history.resource
    gateway = PostgresDockerLifecycleAdapter(provider=provider, authority=authority)
    service = LifecycleService(
        registry=cast(InstanceRegistry, _EmptyRegistry()),
        gateway=gateway,
        journal=JsonlLifecycleJournal(journal_path),
    )
    app = create_production_app(
        database_url="postgresql://unused",
        provider_catalog=_catalog(),
        backend_adapters={"docker": _Backend()},
        acquire_connection=lambda: contextmanager(_connection)(),
        lifecycle_service=service,
    )

    results = app.state.lifecycle_service.run(
        LIFECYCLE_SCOPE, LIFECYCLE_POLICY, LIFECYCLE_AUTHORIZATION, now=LIFECYCLE_NOW
    )

    assert [result.outcome for result in results] == [LifecycleOutcome.QUARANTINED]
    assert provider.mock_calls == [call.quarantine(history.resource)]
