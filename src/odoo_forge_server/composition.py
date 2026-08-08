"""Production composition root for the read-only control-plane edge."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI

from odoo_forge.control_plane.authority import ControlPlaneAuthority
from odoo_forge.control_plane.reconcile import Reconciler
from odoo_forge.data_environments.service import DataEnvironmentService
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.ports.resource_custody import ResourceCustodyAdapter
from odoo_forge.ports.resource_lifecycle import LifecycleSchedulerGate
from odoo_forge.provider_catalog import (
    ProviderCatalog,
    ProviderCatalogResolver,
    ProviderKind,
    ResolvedProviderAdapter,
)
from odoo_forge.resource_lifecycle.service import LifecycleService
from odoo_forge_docker.provider import DockerBackendProvider
from odoo_forge_instances_postgres.adapter import (
    Connection,
    ConnectionAcquirer,
    PostgresInstanceRegistry,
)
from odoo_forge_instances_postgres.data_environment_registry import PostgresDataEnvironmentRegistry
from odoo_forge_instances_postgres.raw_data_grant_authority import PostgresRawDataGrantAuthority
from odoo_forge_postgres_docker.authority import (
    DockerResourceCustodyAdapter,
    LocalOwnershipAuthority,
)
from odoo_forge_postgres_docker.lifecycle import (
    JsonlLifecycleJournal,
    PostgresDockerLifecycleAdapter,
)
from odoo_forge_postgres_docker.provider import DockerPostgresqlDatabaseProvider
from odoo_forge_server.app import UiRuntime, create_app

BackendAdapter = Any

_LIFECYCLE_SCHEDULER_ENV = "ODOO_FORGE_LIFECYCLE_SCHEDULER_ENABLED"


class EnvLifecycleSchedulerGate:
    """Explicit opt-in gate: automated lifecycle runs stay off unless set to exactly "1".

    No composed code path reads this gate to trigger a run automatically; it
    only exists so a future scheduled invoker can refuse to run when the
    operator has not explicitly opted in. Lifecycle execution through
    `LifecycleService.run` remains a manual, directly-callable operation
    regardless of this gate.
    """

    def enabled(self) -> bool:
        return os.environ.get(_LIFECYCLE_SCHEDULER_ENV) == "1"


def _psycopg_acquirer(database_url: str) -> ConnectionAcquirer:
    @contextmanager
    def acquire() -> Iterator[Connection]:
        with psycopg.connect(database_url) as connection:
            yield connection

    return acquire


def _default_resource_authority() -> LocalOwnershipAuthority:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return LocalOwnershipAuthority(state_home / "odoo-forge" / "postgres-docker")


def _default_lifecycle_service(
    registry: InstanceRegistry, authority: LocalOwnershipAuthority
) -> LifecycleService:
    """Compose the dormant PR4 adapter over the SAME registry/authority as custody.

    Kept internal to composition: no HTTP route exposes lifecycle execution.
    `LifecycleService.run` remains available for manual, explicit invocation;
    nothing here schedules or triggers it automatically.
    """
    gateway = PostgresDockerLifecycleAdapter(
        provider=DockerPostgresqlDatabaseProvider(ownership_authority=authority),
        authority=authority,
    )
    journal = JsonlLifecycleJournal(authority.root / "lifecycle.jsonl")
    return LifecycleService(registry=registry, gateway=gateway, journal=journal)


def create_production_app(
    *,
    database_url: str,
    provider_catalog: ProviderCatalog,
    backend_adapters: Mapping[str, BackendAdapter] | None = None,
    acquire_connection: Callable[[], AbstractContextManager[Connection]] | None = None,
    ui_runtime: UiRuntime | None = None,
    custody_adapter: ResourceCustodyAdapter | None = None,
    data_environment_service: DataEnvironmentService | None = None,
    lifecycle_service: LifecycleService | None = None,
    lifecycle_scheduler_gate: LifecycleSchedulerGate | None = None,
) -> FastAPI:
    """Compose approved adapters while injecting only the backend status callable.

    Also wires one internal `ControlPlaneAuthority` over the SAME registry
    instance the reconciler reads, and one internal `LifecycleService` over
    that SAME registry plus a shared `LocalOwnershipAuthority`: no second
    registry, no new HTTP route, no auth, and no automated lifecycle
    execution are added by this wiring. Manual execution stays available
    through `app.state.lifecycle_service.run(...)`; the opt-in scheduler
    gate defaults to disabled.
    """
    resolution = ProviderCatalogResolver(provider_catalog).resolve(ProviderKind.BACKEND)
    if not isinstance(resolution, ResolvedProviderAdapter):
        raise RuntimeError(f"backend provider catalog resolution failed: {resolution.code}")

    adapters = backend_adapters or {resolution.adapter_id: DockerBackendProvider()}
    try:
        backend = adapters[resolution.adapter_id]
    except KeyError as exc:
        raise RuntimeError(
            f"backend provider adapter is unavailable: {resolution.adapter_id}"
        ) from exc
    acquirer = acquire_connection or _psycopg_acquirer(database_url)
    registry: InstanceRegistry = PostgresInstanceRegistry(acquirer)
    reconciler = Reconciler(registry, backend.status)
    authority = _default_resource_authority()
    app = create_app(reconciler=reconciler, ui_runtime=ui_runtime)
    app.state.registry = registry
    app.state.backend_status = backend.status
    app.state.reconciler = reconciler
    app.state.resource_authority = authority
    app.state.control_plane_authority = ControlPlaneAuthority(
        custody_adapter or DockerResourceCustodyAdapter(authority), registry
    )
    app.state.data_environment_registry = PostgresDataEnvironmentRegistry(acquirer)
    app.state.raw_data_grant_authority = PostgresRawDataGrantAuthority(acquirer)
    app.state.data_environment_service = data_environment_service
    app.state.lifecycle_scheduler_gate = lifecycle_scheduler_gate or EnvLifecycleSchedulerGate()
    app.state.lifecycle_service = lifecycle_service or _default_lifecycle_service(
        registry, authority
    )
    return app


__all__ = ["create_production_app"]
