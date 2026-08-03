"""Opt-in server-rendered, read-only operations views."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from odoo_forge.control_plane.models import ReconciliationOutcome, ReconciliationResult
from odoo_forge.instance_registry import InstanceId, InstancePointer
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_server.app import UiRuntime

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


def _guard(request: Request, runtime: UiRuntime) -> None:
    server = request.scope.get("server")
    if not server or server[0] != runtime.bind_host:
        raise HTTPException(status_code=403, detail="read-only UI is loopback-only")


def _render(
    request: Request, name: str, result: ReconciliationResult, *, status: int = 200, **extra: Any
) -> HTMLResponse:
    context = {"result": result, "label": _label(result.outcome), **extra}
    return _TEMPLATES.TemplateResponse(
        request=request, name=name, context=context, status_code=status
    )


def create_ui_router(reconciler: Any, runtime: UiRuntime) -> APIRouter:
    router = APIRouter()

    @router.get(_PREFIX, response_class=HTMLResponse)
    def dashboard(request: Request, tenant_id: str, project_id: str) -> HTMLResponse:
        _guard(request, runtime)
        result = reconciler.list(_scope(tenant_id, project_id))
        return _render(
            request,
            "instances.html",
            result,
            status=503 if result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR else 200,
        )

    @router.get(f"{_PREFIX}/{{instance_id}}", response_class=HTMLResponse)
    def detail(request: Request, tenant_id: str, project_id: str, instance_id: str) -> HTMLResponse:
        _guard(request, runtime)
        result = reconciler.get(
            InstancePointer(
                scope=_scope(tenant_id, project_id), instance_id=InstanceId(value=instance_id)
            )
        )
        if result.outcome is ReconciliationOutcome.EMPTY:
            raise HTTPException(status_code=404, detail="instance not found")
        if result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR:
            return _render(request, "instances.html", result, status=503)
        return _render(request, "instance.html", result, row=result.rows[0])

    return router


__all__ = ["create_ui_router"]
