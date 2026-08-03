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


class MissingReceiptError(InstanceRegistryError):
    """Raised when a registration is submitted without required lineage receipt."""

    def __init__(self, pointer: InstancePointer) -> None:
        self.pointer = pointer
        super().__init__(
            f"registration receipt required: {pointer.scope.project_id}/{pointer.instance_id.value}"
        )


class InstanceRegistrationConflictError(InstanceRegistryError):
    """Raised when a registration reuses an operation identity with different data."""

    def __init__(self, pointer: InstancePointer) -> None:
        self.pointer = pointer
        super().__init__(
            "instance registration conflict: "
            f"{pointer.scope.project_id}/{pointer.instance_id.value}"
        )


class ReceiptOverwriteRejectedError(InstanceRegistryError):
    """Raised when `store()` would rewrite a row that already carries a receipt.

    `store()` is a generic create-or-replace write with no lineage
    semantics; a receipt-bearing row is authoritative and its evidence must
    only ever be extended through `register()`, never silently rewritten or
    cleared by a plain overwrite.
    """

    def __init__(self, pointer: InstancePointer) -> None:
        self.pointer = pointer
        super().__init__(
            "store() cannot overwrite a receipt-bearing row: "
            f"{pointer.scope.project_id}/{pointer.instance_id.value}"
        )


__all__ = [
    "InstanceRecordNotFoundError",
    "InstanceRegistrationConflictError",
    "InstanceRegistryError",
    "MissingReceiptError",
    "ReceiptOverwriteRejectedError",
]
