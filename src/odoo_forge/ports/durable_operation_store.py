"""Provider-neutral persistence contract for durable workflow operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from odoo_forge.durable_operations.service import DurableCheckpoint, TerminalCommitBundle
from odoo_forge.durable_operations.types import (
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
)

# Lifecycles a record may hold while its terminal commit carries residual cleanup entries.
# Those entries are the immutable historical record of what was owed at commit time; the
# lifecycle is the authority on whether the obligation is still open (CLEANUP_REQUIRED) or
# has been resolved (CLOSED). CLOSED belongs here so closing never erases the terminal commit.
_RESIDUAL_LIFECYCLES = frozenset({LifecycleState.CLEANUP_REQUIRED, LifecycleState.CLOSED})


@dataclass(frozen=True)
class DurableOperationRecord:
    """The authoritative durable view returned by persistence operations."""

    identity: DurableOperationIdentity
    revision: OperationRevision
    lifecycle: LifecycleState = LifecycleState.ACCEPTED
    checkpoint: DurableCheckpoint | None = None
    terminal_commit: TerminalCommitBundle | None = None
    recovery_evidence: tuple[RedactedEvidence, ...] = ()

    def __post_init__(self) -> None:
        """Keep terminal lifecycle visibility aligned with authoritative cleanup facts."""
        if self.terminal_commit is None:
            return

        if self.terminal_commit.residual_cleanup:
            if self.lifecycle not in _RESIDUAL_LIFECYCLES:
                raise ValueError(
                    "terminal commits with residual cleanup must surface "
                    "cleanup_required lifecycle until the obligation is resolved as closed"
                )
            return

        if self.lifecycle is not self.terminal_commit.outcome:
            raise ValueError(
                "terminal commits without residual cleanup must expose "
                "their terminal outcome lifecycle"
            )


@runtime_checkable
class DurableOperationStore(Protocol):
    """Persist replay-safe state without selecting an adapter or scheduler."""

    def create_or_load(self, identity: DurableOperationIdentity) -> DurableOperationRecord:
        """Atomically create an identity binding or return its same-digest replay."""
        ...

    def save_checkpoint(
        self,
        operation_id: str,
        expected_revision: OperationRevision,
        checkpoint: DurableCheckpoint,
    ) -> DurableOperationRecord:
        """Append or replace resume-safe progress only when the revision still matches.

        A successful write advances the record to exactly ``checkpoint.revision + 1``.
        Raise ``RevisionConflictError`` when ``expected_revision`` no longer matches the
        durable record.
        """
        ...

    def mark_reconciliation_required(
        self, operation_id: str, expected_revision: OperationRevision
    ) -> DurableOperationRecord:
        """Durably surface an unknown mutation outcome for workflow reconciliation.

        Raise ``RevisionConflictError`` when ``expected_revision`` no longer matches the
        durable record.
        """
        ...

    def commit_terminal(
        self, operation_id: str, bundle: TerminalCommitBundle
    ) -> DurableOperationRecord:
        """Compare-and-swap the complete terminal bundle as one authoritative result.

        Raise ``RevisionConflictError`` when ``bundle.expected_revision`` no longer matches
        the durable record.
        """
        ...

    def resolve_residual(
        self, operation_id: str, expected_revision: OperationRevision
    ) -> DurableOperationRecord:
        """Close a recorded cleanup obligation only when its revision still matches.

        Closing resolves the obligation; it MUST NOT erase the authoritative terminal
        commit. The returned record has ``lifecycle=CLOSED`` and RETAINS its
        ``terminal_commit`` — outcome, redacted evidence, and the residual entries that
        were recorded, so the operation stays auditable after cleanup.

        Raise ``InvalidLifecycleTransitionError`` when the record carries no open residual
        obligation; closing is not a no-op and MUST NOT report a resolution that never happened.
        Raise ``RevisionConflictError`` when ``expected_revision`` no longer matches the
        durable record.
        """
        ...

    def list_recoverable(self) -> tuple[DurableOperationRecord, ...]:
        """Return non-authoritative or cleanup-required records for workflow recovery."""
        ...


__all__ = ["DurableOperationRecord", "DurableOperationStore"]
