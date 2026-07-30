"""Typed, provider-neutral errors for the instance state registry."""

from odoo_forge.instance_registry.types import InstancePointer


class InstanceRegistryError(Exception):
    """Base class for instance registry contract failures."""


class InstanceRecordNotFoundError(InstanceRegistryError):
    """Raised when a requested instance record is not registered."""

    def __init__(self, pointer: InstancePointer) -> None:
        self.pointer = pointer
        super().__init__(
            f"instance record not found: {pointer.scope.project_id}/{pointer.instance_id.value}"
        )


__all__ = ["InstanceRecordNotFoundError", "InstanceRegistryError"]
