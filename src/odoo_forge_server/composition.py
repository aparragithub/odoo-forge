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
from odoo_forge.provider_catalog import (
    ProviderCatalog,
    ProviderCatalogResolver,
    ProviderKind,
    ResolvedProviderAdapter,
)
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
from odoo_forge_server.app import UiRuntime, create_app

BackendAdapter = Any


def _psycopg_acquirer(database_url: str) -> ConnectionAcquirer:
    @contextmanager
    def acquire() -> Iterator[Connection]:
        with psycopg.connect(database_url) as connection:
            yield connection

    return acquire


def _default_custody_adapter() -> ResourceCustodyAdapter:
    """Build the production Docker custody adapter under its default local root.

    Kept internal to composition: the authority coordinator is wired for
    fail-closed custody confirmation, but no HTTP route exposes it — reads
    remain the only externally reachable behavior.
    """
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    root = state_home / "odoo-forge" / "postgres-docker"
    return DockerResourceCustodyAdapter(LocalOwnershipAuthority(root))


def create_production_app(
    *,
    database_url: str,
    provider_catalog: ProviderCatalog,
    backend_adapters: Mapping[str, BackendAdapter] | None = None,
    acquire_connection: Callable[[], AbstractContextManager[Connection]] | None = None,
    ui_runtime: UiRuntime | None = None,
    custody_adapter: ResourceCustodyAdapter | None = None,
    data_environment_service: DataEnvironmentService | None = None,
) -> FastAPI:
    """Compose approved adapters while injecting only the backend status callable.

    Also wires one internal `ControlPlaneAuthority` over the SAME registry
    instance the reconciler reads: no second registry, no new HTTP route, no
    auth, and no lifecycle execution are added by this wiring.
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
    app = create_app(reconciler=reconciler, ui_runtime=ui_runtime)
    app.state.registry = registry
    app.state.backend_status = backend.status
    app.state.reconciler = reconciler
    app.state.control_plane_authority = ControlPlaneAuthority(
        custody_adapter or _default_custody_adapter(), registry
    )
    app.state.data_environment_registry = PostgresDataEnvironmentRegistry(acquirer)
    app.state.raw_data_grant_authority = PostgresRawDataGrantAuthority(acquirer)
    app.state.data_environment_service = data_environment_service
    return app


__all__ = ["create_production_app"]
