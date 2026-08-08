"""Read-only instance reconciliation routes."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from odoo_forge.backend.status import InstanceStatus
from odoo_forge.control_plane.models import (
    ReconciliationOutcome,
    ReconciliationResult,
)
from odoo_forge.instance_registry import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.manifest.schema import Manifest
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_server.runtime import UiRuntime, guard_loopback_request

ManifestLoader = Callable[[Path], object]


class ReconciliationRowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: InstanceRecord
    live: InstanceStatus | None
    outcome: ReconciliationOutcome
    detail: str | None = None


class ReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ReconciliationOutcome
    rows: tuple[ReconciliationRowResponse, ...]
    detail: str | None = None


class ManifestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    odoo_version: str
    edition: str
    layer_names: tuple[str, ...]
    backend_bind_host: str | None
    backend_http_port: int | None


class ManifestContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["valid", "unavailable", "invalid"]
    summary: ManifestSummary | None = None


_PREFIX = "/api/v1/tenants/{tenant_id}/projects/{project_id}/instances"
_MANIFEST_PREFIX = "/api/v1/tenants/{tenant_id}/projects/{project_id}/manifest"


def _scope(tenant_id: str, project_id: str) -> ProjectScope:
    return ProjectScope(tenant=TenantId(value=tenant_id), project_id=project_id)


def _response(result: ReconciliationResult, *, single: bool = False) -> ReconciliationResponse:
    if result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR:
        raise HTTPException(status_code=503, detail="instance registry unavailable")
    if single and result.outcome is ReconciliationOutcome.EMPTY:
        raise HTTPException(status_code=404, detail="instance not found")
    return ReconciliationResponse.model_validate(result.model_dump())


def _manifest_context(location: Path, loader: ManifestLoader) -> ManifestContextResponse:
    try:
        raw = loader(location)
    except Exception:
        return ManifestContextResponse(status="unavailable")
    try:
        manifest = Manifest.model_validate(raw)
    except ValidationError:
        return ManifestContextResponse(status="invalid")
    backend = manifest.backend.odoo if manifest.backend is not None else None
    return ManifestContextResponse(
        status="valid",
        summary=ManifestSummary(
            project_name=manifest.name,
            odoo_version=manifest.odoo_version,
            edition=manifest.edition,
            layer_names=tuple(layer.name for layer in manifest.layers),
            backend_bind_host=backend.bind_host if backend is not None else None,
            backend_http_port=backend.http_port if backend is not None else None,
        ),
    )


def create_instances_router(
    reconciler: Any,
    *,
    runtime: UiRuntime | None = None,
    manifest_scope: ProjectScope | None = None,
    manifest_location: Path | None = None,
    manifest_loader: ManifestLoader | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get(_PREFIX, response_model=ReconciliationResponse)
    def list_instances(tenant_id: str, project_id: str) -> ReconciliationResponse:
        return _response(reconciler.list(_scope(tenant_id, project_id)))

    @router.get(f"{_PREFIX}/{{instance_id}}", response_model=ReconciliationResponse)
    def get_instance(tenant_id: str, project_id: str, instance_id: str) -> ReconciliationResponse:
        pointer = InstancePointer(
            scope=_scope(tenant_id, project_id), instance_id=InstanceId(value=instance_id)
        )
        return _response(reconciler.get(pointer), single=True)

    if (
        runtime is not None
        and manifest_scope is not None
        and manifest_location is not None
        and manifest_loader is not None
    ):

        @router.get(_MANIFEST_PREFIX, response_model=ManifestContextResponse)
        def get_manifest_context(
            request: Request, tenant_id: str, project_id: str
        ) -> ManifestContextResponse:
            guard_loopback_request(request, runtime)
            if _scope(tenant_id, project_id) != manifest_scope:
                raise HTTPException(status_code=404, detail="manifest not found")
            return _manifest_context(manifest_location, manifest_loader)

    return router


__all__ = [
    "ManifestContextResponse",
    "ManifestLoader",
    "ManifestSummary",
    "ReconciliationResponse",
    "ReconciliationRowResponse",
    "create_instances_router",
]
