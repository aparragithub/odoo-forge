from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.types import InstancePointer
from odoo_forge.resource_ownership.types import OwnershipReceipt, ResourceOwnership, ResourceRef


class CustodyTransition(StrEnum):
    RESERVE_BIND_ACTIVATE = "reserve_bind_activate"


class CustodyStartingState(StrEnum):
    UNRESERVED = "unreserved"


def custody_request_digest(
    *,
    pointer: InstancePointer,
    resource: ResourceRef,
    resource_name: str,
    resource_id: str,
    starting_state: CustodyStartingState,
    requested_transition: CustodyTransition,
) -> str:
    payload = {
        "tenant": pointer.scope.tenant.value,
        "project": pointer.scope.project_id,
        "instance": pointer.instance_id.value,
        "resource_identifier": resource.identifier,
        "resource_kind": resource.resource_kind,
        "resource_ownership": resource.ownership.value,
        "resource_name": resource_name,
        "resource_id": resource_id,
        "starting_state": starting_state.value,
        "requested_transition": requested_transition.value,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CustodyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    operation: DurableOperationIdentity
    pointer: InstancePointer
    resource: ResourceRef
    resource_name: str
    resource_id: str
    starting_state: CustodyStartingState
    requested_transition: CustodyTransition

    @model_validator(mode="after")
    def validate_contract(self) -> CustodyRequest:
        if not self.operation.operation_id.startswith("postgres-docker:"):
            raise ValueError("unsupported custody operation")
        if not self.operation.operation_id.removeprefix("postgres-docker:").strip():
            raise ValueError("custody operation token is required")
        if self.resource_name != self.resource.identifier:
            raise ValueError("custody resource name must match its identifier")
        expected = custody_request_digest(
            pointer=self.pointer,
            resource=self.resource,
            resource_name=self.resource_name,
            resource_id=self.resource_id,
            starting_state=self.starting_state,
            requested_transition=self.requested_transition,
        )
        if self.operation.request_digest != expected:
            raise ValueError("custody request digest does not match request meaning")
        if (
            self.resource.resource_kind != "container"
            or self.resource.ownership is not ResourceOwnership.CREATED
        ):
            raise ValueError("unsupported custody resource")
        return self


class CustodyTransitionConflictError(Exception):
    pass


class CustodyUnverifiableError(Exception):
    pass


class ResourceCustodyAdapter(Protocol):
    def confirm(self, request: CustodyRequest) -> OwnershipReceipt: ...
