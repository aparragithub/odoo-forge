from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.types import InstancePointer
from odoo_forge.resource_ownership.types import OwnershipReceipt, ResourceOwnership, ResourceRef

_PROVIDER_SEPARATOR = ":"


class CustodyTransition(StrEnum):
    RESERVE_BIND_ACTIVATE = "reserve_bind_activate"


class CustodyStartingState(StrEnum):
    UNRESERVED = "unreserved"


def custody_operation_parts(operation_id: str) -> tuple[str, str]:
    """Split a provider-qualified custody operation id into provider and token.

    The core enforces the SHAPE of the identity, never a specific provider
    name: naming one provider here would put infrastructure knowledge in the
    domain and force an edit for every future provider. Each adapter asserts
    its own provider on the parsed value instead.

    Surrounding whitespace is rejected rather than normalized. The raw
    `operation_id` becomes a durable authority record key, so `"pg: op-a "`
    and `"pg:op-a"` must not be two spellings of one custody identity.
    """
    provider, separator, token = operation_id.partition(_PROVIDER_SEPARATOR)
    if not separator:
        raise ValueError("custody operation must be provider-qualified")
    if not provider or provider != provider.strip():
        raise ValueError("custody operation provider is required")
    if not token or token != token.strip():
        raise ValueError("custody operation token is required")
    return provider, token


def custody_request_digest(
    *,
    operation_id: str,
    pointer: InstancePointer,
    resource: ResourceRef,
    resource_name: str,
    resource_id: str,
    starting_state: CustodyStartingState,
    requested_transition: CustodyTransition,
) -> str:
    payload = {
        "operation_id": operation_id,
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
    resource_name: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    starting_state: CustodyStartingState
    requested_transition: CustodyTransition

    @model_validator(mode="after")
    def validate_contract(self) -> CustodyRequest:
        custody_operation_parts(self.operation.operation_id)
        if self.resource_name != self.resource.identifier:
            raise ValueError("custody resource name must match its identifier")
        expected = custody_request_digest(
            operation_id=self.operation.operation_id,
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


class CustodyError(Exception):
    """Any custody failure.

    Kept message-free so no credential material can reach an exception
    string, and shared so a caller can handle every custody failure without
    enumerating each subclass.
    """


class CustodyTransitionConflictError(CustodyError):
    pass


class CustodyUnverifiableError(CustodyError):
    pass


class ResourceCustodyAdapter(Protocol):
    def confirm(self, request: CustodyRequest) -> OwnershipReceipt: ...
