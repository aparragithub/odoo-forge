"""Synchronous control-plane authority coordinating custody and registration.

Composes the existing custody seam and instance registry into one internal
write boundary: it never redefines tenancy, ownership, or transition
vocabulary, and it is the only place callers submit an accepted registration.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry import (
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
    InstanceRegistrationConflictError,
)
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.ports.resource_custody import (
    CustodyRequest,
    CustodyStartingState,
    CustodyTransition,
    ResourceCustodyAdapter,
)
from odoo_forge.resource_ownership.types import ResourceRef


class RegistrationRequest(BaseModel):
    """Immutable input to `ControlPlaneAuthority.register`.

    Carries the same identity/resource meaning as `CustodyRequest`, minus the
    custody starting state and requested transition: this authority always
    requests the sole supported `unreserved -> active` transition, so a
    caller never repeats that boilerplate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    operation: DurableOperationIdentity
    pointer: InstancePointer
    resource: ResourceRef
    resource_name: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)


class RegistrationValidationError(Exception):
    """Raised when a registration request's meaning cannot be validated."""


class ControlPlaneAuthority:
    """Coordinate one fail-closed custody transition and its canonical registration."""

    def __init__(self, custody: ResourceCustodyAdapter, registry: InstanceRegistry) -> None:
        self._custody = custody
        self._registry = registry

    def register(self, request: RegistrationRequest) -> InstanceRecord:
        """Accept one registration, coordinating custody once and committing canonically.

        Checks any already-committed row for this pointer BEFORE touching
        custody: an exact match returns it unchanged (idempotent retry, no
        second Docker transition); a materially different match is a typed
        conflict. Only a genuinely new pointer reaches custody confirmation.
        A commit failure after custody has already succeeded is retried
        exactly once against the registry — never against custody again, and
        never looped further.
        """
        custody_request = self._custody_request(request)

        existing = self._existing_record(request.pointer)
        if existing is not None:
            if _matches(existing, request):
                return existing
            raise InstanceRegistrationConflictError(request.pointer)

        receipt = self._custody.confirm(custody_request)
        record = InstanceRecord(pointer=request.pointer, resource=request.resource, receipt=receipt)
        try:
            return self._registry.register(record)
        except InstanceRegistrationConflictError:
            raise
        except Exception:
            return self._registry.register(record)

    def _existing_record(self, pointer: InstancePointer) -> InstanceRecord | None:
        try:
            return self._registry.get(pointer)
        except InstanceRecordNotFoundError:
            return None

    @staticmethod
    def _custody_request(request: RegistrationRequest) -> CustodyRequest:
        try:
            return CustodyRequest(
                operation=request.operation,
                pointer=request.pointer,
                resource=request.resource,
                resource_name=request.resource_name,
                resource_id=request.resource_id,
                starting_state=CustodyStartingState.UNRESERVED,
                requested_transition=CustodyTransition.RESERVE_BIND_ACTIVATE,
            )
        except ValidationError as exc:
            raise RegistrationValidationError() from exc


def _matches(existing: InstanceRecord, request: RegistrationRequest) -> bool:
    """Report whether a committed row already represents this exact request."""
    return (
        existing.pointer == request.pointer
        and existing.resource == request.resource
        and existing.receipt is not None
        and existing.receipt.operation == request.operation
        and existing.receipt.owned_resource_ids == (request.resource_id,)
    )


__all__ = ["ControlPlaneAuthority", "RegistrationRequest", "RegistrationValidationError"]
