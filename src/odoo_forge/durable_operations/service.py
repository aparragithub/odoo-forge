"""Pure transition rules for provider-neutral durable operations."""

from dataclasses import dataclass
from enum import StrEnum

from odoo_forge.durable_operations.errors import (
    IncompleteTerminalCommitError,
    InvalidLifecycleTransitionError,
    ReplayConflictError,
    UnsafeCompensationError,
)
from odoo_forge.durable_operations.types import (
    CompensationScope,
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
)


class RecoveryAction(StrEnum):
    """Workflow-level actions derived from durable facts."""

    RESUME = "resume"
    RECONCILE = "reconcile"
    SURFACE_RESIDUAL = "surface_residual"


@dataclass(frozen=True)
class DurableCheckpoint:
    """Resume-safe progress captured after a durable workflow change."""

    revision: OperationRevision
    phase: str
    evidence: RedactedEvidence


@dataclass(frozen=True)
class RecoveryPlan:
    """A provider-neutral recovery decision based on known durable facts."""

    action: RecoveryAction
    revision: OperationRevision
    checkpoint: DurableCheckpoint | None
    reason: str


@dataclass(frozen=True)
class TerminalCommitBundle:
    """The complete unit required for one authoritative terminal publication."""

    expected_revision: OperationRevision
    outcome: LifecycleState
    evidence: tuple[RedactedEvidence, ...]
    residual_cleanup: tuple[RedactedEvidence, ...]


_LIFECYCLE_ORDER = {
    LifecycleState.ACCEPTED: 0,
    LifecycleState.IN_PROGRESS: 1,
    LifecycleState.RECONCILIATION_REQUIRED: 2,
    LifecycleState.TERMINAL_PENDING: 3,
    LifecycleState.SUCCEEDED: 4,
    LifecycleState.FAILED: 4,
    LifecycleState.CLEANUP_REQUIRED: 5,
    LifecycleState.CLOSED: 6,
}
_TERMINAL_OUTCOMES = frozenset({LifecycleState.SUCCEEDED, LifecycleState.FAILED})
_UNKNOWN_OUTCOME_REASON = "mutation outcome is unknown without a durable checkpoint"


def _next_revision(revision: OperationRevision) -> OperationRevision:
    """Return the next monotonic durable revision."""
    return OperationRevision(value=revision.value + 1)


def replay_or_conflict(
    recorded: DurableOperationIdentity, submitted_request_digest: str
) -> DurableOperationIdentity:
    """Return a safe replay or reject reuse of an identity for another request."""
    if not recorded.matches_request_digest(submitted_request_digest):
        raise ReplayConflictError(
            operation_id=recorded.operation_id,
            recorded_request_digest=recorded.request_digest,
            submitted_request_digest=submitted_request_digest,
        )
    return recorded


def advance_lifecycle(
    current: LifecycleState,
    revision: OperationRevision,
    target: LifecycleState,
) -> tuple[LifecycleState, OperationRevision]:
    """Advance a lifecycle state without allowing regression or terminal-outcome flips."""
    if _LIFECYCLE_ORDER[target] < _LIFECYCLE_ORDER[current]:
        raise InvalidLifecycleTransitionError(f"cannot regress from {current} to {target}")
    if current in _TERMINAL_OUTCOMES and target in _TERMINAL_OUTCOMES and target is not current:
        raise InvalidLifecycleTransitionError(
            f"cannot overwrite authoritative terminal outcome {current} with {target}"
        )
    return target, _next_revision(revision)


def save_checkpoint(
    revision: OperationRevision, phase: str, evidence: RedactedEvidence
) -> DurableCheckpoint:
    """Create a checkpoint for facts that are safe to use during recovery."""
    if not phase:
        raise ValueError("checkpoint phase must not be empty")
    return DurableCheckpoint(revision=revision, phase=phase, evidence=evidence)


def plan_recovery(
    state: LifecycleState,
    revision: OperationRevision,
    checkpoint: DurableCheckpoint | None,
    *,
    mutation_attempted: bool,
) -> RecoveryPlan:
    """Choose workflow recovery without interpreting provider-specific status."""
    if state is LifecycleState.CLEANUP_REQUIRED:
        return RecoveryPlan(
            action=RecoveryAction.SURFACE_RESIDUAL,
            revision=revision,
            checkpoint=checkpoint,
            reason="residual cleanup remains open",
        )
    if state is LifecycleState.RECONCILIATION_REQUIRED:
        return RecoveryPlan(
            action=RecoveryAction.RECONCILE,
            revision=revision,
            checkpoint=checkpoint,
            reason="mutation outcome requires reconciliation",
        )
    if mutation_attempted and checkpoint is None:
        return RecoveryPlan(
            action=RecoveryAction.RECONCILE,
            revision=revision,
            checkpoint=None,
            reason=_UNKNOWN_OUTCOME_REASON,
        )
    if checkpoint is not None:
        return RecoveryPlan(
            action=RecoveryAction.RESUME,
            revision=_next_revision(checkpoint.revision),
            checkpoint=checkpoint,
            reason="resume from durable checkpoint",
        )
    return RecoveryPlan(
        action=RecoveryAction.RESUME,
        revision=revision,
        checkpoint=None,
        reason="no mutation has been attempted",
    )


def build_terminal_commit(
    expected_revision: OperationRevision,
    outcome: LifecycleState,
    evidence: tuple[RedactedEvidence, ...],
    residual_cleanup: tuple[RedactedEvidence, ...],
) -> TerminalCommitBundle:
    """Build a complete atomic terminal publication unit or reject it."""
    if outcome not in _TERMINAL_OUTCOMES:
        raise IncompleteTerminalCommitError("terminal outcome must be succeeded or failed")
    if not evidence:
        raise IncompleteTerminalCommitError("terminal commit requires durable evidence")
    return TerminalCommitBundle(
        expected_revision=expected_revision,
        outcome=outcome,
        evidence=evidence,
        residual_cleanup=residual_cleanup,
    )


def ensure_compensation_target(scope: CompensationScope, resource_id: str) -> str:
    """Return an owned resource ID or reject unsafe compensation."""
    if not scope.owns(resource_id):
        raise UnsafeCompensationError(
            f"resource '{resource_id}' is not owned by operation '{scope.operation_id}'"
        )
    return resource_id


__all__ = [
    "DurableCheckpoint",
    "RecoveryAction",
    "RecoveryPlan",
    "TerminalCommitBundle",
    "advance_lifecycle",
    "build_terminal_commit",
    "ensure_compensation_target",
    "plan_recovery",
    "replay_or_conflict",
    "save_checkpoint",
]
