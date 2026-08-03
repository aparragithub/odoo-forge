"""Read-only instance reconciliation routes."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from odoo_forge.backend.status import InstanceStatus
from odoo_forge.control_plane.models import (
    ReconciliationOutcome,
    ReconciliationResult,
)
from odoo_forge.instance_registry import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.tenancy import ProjectScope, TenantId


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


_PREFIX = "/api/v1/tenants/{tenant_id}/projects/{project_id}/instances"


def _scope(tenant_id: str, project_id: str) -> ProjectScope:
    return ProjectScope(tenant=TenantId(value=tenant_id), project_id=project_id)


def _response(result: ReconciliationResult, *, single: bool = False) -> ReconciliationResponse:
    if result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR:
        raise HTTPException(status_code=503, detail="instance registry unavailable")
    if single and result.outcome is ReconciliationOutcome.EMPTY:
        raise HTTPException(status_code=404, detail="instance not found")
    return ReconciliationResponse.model_validate(result.model_dump())


def create_instances_router(reconciler: Any) -> APIRouter:
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

    return router


__all__ = ["ReconciliationResponse", "ReconciliationRowResponse", "create_instances_router"]
