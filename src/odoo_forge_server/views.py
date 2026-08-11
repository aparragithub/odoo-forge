"""Opt-in server-rendered, read-only operations views."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from odoo_forge.control_plane.models import ReconciliationOutcome, ReconciliationResult
from odoo_forge.instance_registry import InstanceId, InstancePointer
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_server.routes.instances import (
    ManifestContextResponse,
    ManifestLoader,
    _manifest_context,
)
from odoo_forge_server.runtime import UiRuntime, guard_loopback_request

_PREFIX = "/ui/tenants/{tenant_id}/projects/{project_id}/instances"
_TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
_LABELS = {
    ReconciliationOutcome.FRESH: "fresh",
    ReconciliationOutcome.DRIFTED: "drifted",
    ReconciliationOutcome.STALE_UNVERIFIED: "stale/unverified",
    ReconciliationOutcome.EMPTY: "empty",
    ReconciliationOutcome.PERSISTENCE_ERROR: "persistence-error",
    ReconciliationOutcome.PARTIAL_FAILURE: "partial-failure",
}


def _scope(tenant_id: str, project_id: str) -> ProjectScope:
    return ProjectScope(tenant=TenantId(value=tenant_id), project_id=project_id)


def _label(outcome: ReconciliationOutcome) -> str:
    return _LABELS[outcome]


def _render(
    request: Request, name: str, result: ReconciliationResult, *, status: int = 200, **extra: Any
) -> HTMLResponse:
    rows = tuple(
        {
            "value": row,
            "label": _label(row.outcome),
            "is_drifted": row.outcome is ReconciliationOutcome.DRIFTED,
        }
        for row in result.rows
    )
    context = {
        "result": result,
        "label": _label(result.outcome),
        "is_persistence_error": result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR,
        "rows": rows,
        **extra,
    }
    return _TEMPLATES.TemplateResponse(
        request=request, name=name, context=context, status_code=status
    )


def create_ui_router(
    reconciler: Any,
    runtime: UiRuntime,
    *,
    manifest_scope: ProjectScope | None = None,
    manifest_location: Path | None = None,
    manifest_loader: ManifestLoader | None = None,
) -> APIRouter:
    """Create loopback-guarded, read-only HTML reconciliation routes."""
    router = APIRouter()

    @router.get(_PREFIX, response_class=HTMLResponse)
    def dashboard(request: Request, tenant_id: str, project_id: str) -> HTMLResponse:
        guard_loopback_request(request, runtime)
        scope = _scope(tenant_id, project_id)
        manifest: ManifestContextResponse | None = None
        if (
            manifest_scope is not None
            and manifest_location is not None
            and manifest_loader is not None
            and scope == manifest_scope
        ):
            manifest = _manifest_context(manifest_location, manifest_loader)
        result = reconciler.list(scope)
        return _render(
            request,
            "instances.html",
            result,
            status=503 if result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR else 200,
            manifest=manifest,
        )

    @router.get(f"{_PREFIX}/{{instance_id}}", response_class=HTMLResponse)
    def detail(request: Request, tenant_id: str, project_id: str, instance_id: str) -> HTMLResponse:
        guard_loopback_request(request, runtime)
        result = reconciler.get(
            InstancePointer(
                scope=_scope(tenant_id, project_id), instance_id=InstanceId(value=instance_id)
            )
        )
        if result.outcome is ReconciliationOutcome.EMPTY:
            raise HTTPException(status_code=404, detail="instance not found")
        if result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR:
            return _render(request, "instances.html", result, status=503)
        return _render(
            request,
            "instance.html",
            result,
            row=result.rows[0],
            is_drifted=result.rows[0].outcome is ReconciliationOutcome.DRIFTED,
        )

    return router


__all__ = ["create_ui_router"]
