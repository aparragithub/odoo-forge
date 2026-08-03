"""Production composition root for the read-only control-plane edge."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import psycopg
from fastapi import FastAPI

from odoo_forge.control_plane.reconcile import Reconciler
from odoo_forge.ports.instance_registry import InstanceRegistry
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
from odoo_forge_server.app import UiRuntime, create_app

BackendAdapter = Any


def _psycopg_acquirer(database_url: str) -> ConnectionAcquirer:
    @contextmanager
    def acquire() -> Iterator[Connection]:
        with psycopg.connect(database_url) as connection:
            yield connection

    return acquire


def create_production_app(
    *,
    database_url: str,
    provider_catalog: ProviderCatalog,
    backend_adapters: Mapping[str, BackendAdapter] | None = None,
    acquire_connection: Callable[[], AbstractContextManager[Connection]] | None = None,
    ui_runtime: UiRuntime | None = None,
) -> FastAPI:
    """Compose approved adapters while injecting only the backend status callable."""
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
    return app


__all__ = ["create_production_app"]
