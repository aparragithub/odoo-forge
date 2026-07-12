"""Provider-neutral contracts for durable workflow operations."""

from odoo_forge.durable_operations.errors import (
    DurableOperationError,
    IncompleteTerminalCommitError,
    InvalidLifecycleTransitionError,
    ReplayConflictError,
    RevisionConflictError,
    UnknownOperationOutcomeError,
    UnsafeCompensationError,
)
from odoo_forge.durable_operations.types import (
    CompensationScope,
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
)

__all__ = [
    "CompensationScope",
    "DurableOperationError",
    "DurableOperationIdentity",
    "IncompleteTerminalCommitError",
    "InvalidLifecycleTransitionError",
    "LifecycleState",
    "OperationRevision",
    "RedactedEvidence",
    "ReplayConflictError",
    "RevisionConflictError",
    "UnknownOperationOutcomeError",
    "UnsafeCompensationError",
]
