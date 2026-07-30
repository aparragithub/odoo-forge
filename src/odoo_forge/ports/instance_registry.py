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


__all__ = ["InstanceRegistry"]
