"""Core structural port for the provider-neutral instance state registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from odoo_forge.instance_registry.types import InstancePointer, InstanceRecord
from odoo_forge.tenancy.types import ProjectScope


@runtime_checkable
class InstanceRegistry(Protocol):
    """Store, retrieve, and list immutable instance records."""

    def store(self, record: InstanceRecord) -> InstanceRecord:
        """Create or replace a record and return the authoritative value."""
        pass

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        """Return a record or raise the typed not-found domain error."""
        pass

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        """Return records in the scope in deterministic instance-id order."""
        pass

    def register(self, record: InstanceRecord) -> InstanceRecord:
        """Persist one receipt-bearing registration; compare, never replace.

        Requires `record.receipt`. Looks up any existing row by the
        receipt's operation identity: an exact match returns that row
        unchanged (idempotent retry, no second write); a materially
        different match raises without mutating existing state.
        """
        pass


__all__ = ["InstanceRegistry"]
