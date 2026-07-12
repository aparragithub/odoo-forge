"""Typed, redacted durable-operation failures."""

from odoo_forge.durable_operations.types import OperationRevision


class DurableOperationError(Exception):
    """Base class for durable-operation contract failures."""


class ReplayConflictError(DurableOperationError):
    """Raised when an operation ID is reused for a different request digest."""

    def __init__(
        self,
        operation_id: str,
        recorded_request_digest: str,
        submitted_request_digest: str,
    ) -> None:
        self.operation_id = operation_id
        self.recorded_request_digest = recorded_request_digest
        self.submitted_request_digest = submitted_request_digest
        super().__init__(
            "operation "
            f"'{operation_id}' is bound to request digest '{recorded_request_digest}', "
            f"not '{submitted_request_digest}'"
        )


class RevisionConflictError(DurableOperationError):
    """Raised when a durable compare-and-swap loses to a concurrent writer."""

    def __init__(
        self,
        operation_id: str,
        expected_revision: OperationRevision,
        actual_revision: OperationRevision,
    ) -> None:
        self.operation_id = operation_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"operation '{operation_id}' expected revision {expected_revision.value}, "
            f"but the durable record is at revision {actual_revision.value}"
        )


class InvalidLifecycleTransitionError(DurableOperationError):
    """Raised when a transition would regress the durable lifecycle."""


class UnknownOperationOutcomeError(DurableOperationError):
    """Raised when recovery must reconcile an outcome before declaring it authoritative."""


class IncompleteTerminalCommitError(DurableOperationError):
    """Raised when a terminal commit lacks required evidence or cleanup state."""


class UnsafeCompensationError(DurableOperationError):
    """Raised when compensation would target a resource outside its owned scope."""


__all__ = [
    "DurableOperationError",
    "IncompleteTerminalCommitError",
    "InvalidLifecycleTransitionError",
    "ReplayConflictError",
    "RevisionConflictError",
    "UnknownOperationOutcomeError",
    "UnsafeCompensationError",
]
