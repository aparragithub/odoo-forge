from __future__ import annotations

import inspect

import pytest

from odoo_forge.durable_operations import (
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
    RevisionConflictError,
)
from odoo_forge.durable_operations.service import DurableCheckpoint, TerminalCommitBundle
from odoo_forge.ports.durable_operation_recovery import DurableOperationRecovery
from odoo_forge.ports.durable_operation_store import DurableOperationRecord, DurableOperationStore


def _identity() -> DurableOperationIdentity:
    return DurableOperationIdentity(operation_id="operation-42", request_digest="request-42")


def _evidence() -> RedactedEvidence:
    return RedactedEvidence(event="checkpoint", summary="provider mutation acknowledged")


def _checkpoint(revision: int = 1) -> DurableCheckpoint:
    return DurableCheckpoint(
        revision=OperationRevision(value=revision),
        phase="provider-acknowledged",
        evidence=_evidence(),
    )


def _terminal_bundle(
    revision: int = 2,
    *,
    outcome: LifecycleState = LifecycleState.SUCCEEDED,
    residual_cleanup: tuple[RedactedEvidence, ...] = (),
) -> TerminalCommitBundle:
    return TerminalCommitBundle(
        expected_revision=OperationRevision(value=revision),
        outcome=outcome,
        evidence=(_evidence(),),
        residual_cleanup=residual_cleanup,
    )


class _ConformingDurableOperationStore:
    def __init__(self, current_revision: OperationRevision | None = None) -> None:
        self._current_revision = current_revision

    def _guard_revision(self, operation_id: str, expected_revision: OperationRevision) -> None:
        """Reject a compare-and-swap whose expected revision lost to a concurrent writer."""
        if self._current_revision is None or self._current_revision == expected_revision:
            return
        raise RevisionConflictError(
            operation_id=operation_id,
            expected_revision=expected_revision,
            actual_revision=self._current_revision,
        )

    def create_or_load(self, identity: DurableOperationIdentity) -> DurableOperationRecord:
        return DurableOperationRecord(identity=identity, revision=OperationRevision(value=0))

    def save_checkpoint(
        self,
        operation_id: str,
        expected_revision: OperationRevision,
        checkpoint: DurableCheckpoint,
    ) -> DurableOperationRecord:
        self._guard_revision(operation_id, expected_revision)
        return DurableOperationRecord(
            identity=_identity(),
            revision=OperationRevision(value=expected_revision.value + 1),
            lifecycle=LifecycleState.IN_PROGRESS,
            checkpoint=checkpoint,
        )

    def mark_reconciliation_required(
        self, operation_id: str, expected_revision: OperationRevision
    ) -> DurableOperationRecord:
        self._guard_revision(operation_id, expected_revision)
        return DurableOperationRecord(
            identity=_identity(),
            revision=OperationRevision(value=expected_revision.value + 1),
            lifecycle=LifecycleState.RECONCILIATION_REQUIRED,
        )

    def commit_terminal(
        self, operation_id: str, bundle: TerminalCommitBundle
    ) -> DurableOperationRecord:
        self._guard_revision(operation_id, bundle.expected_revision)
        return DurableOperationRecord(
            identity=_identity(),
            revision=OperationRevision(value=bundle.expected_revision.value + 1),
            lifecycle=(
                LifecycleState.CLEANUP_REQUIRED
                if bundle.residual_cleanup
                else bundle.outcome
            ),
            terminal_commit=bundle,
        )

    def resolve_residual(
        self, operation_id: str, expected_revision: OperationRevision
    ) -> DurableOperationRecord:
        self._guard_revision(operation_id, expected_revision)
        return DurableOperationRecord(
            identity=_identity(),
            revision=OperationRevision(value=expected_revision.value + 1),
            lifecycle=LifecycleState.CLOSED,
        )

    def list_recoverable(self) -> tuple[DurableOperationRecord, ...]:
        return (
            DurableOperationRecord(
                identity=_identity(),
                revision=OperationRevision(value=2),
                lifecycle=LifecycleState.RECONCILIATION_REQUIRED,
                checkpoint=_checkpoint(2),
            ),
        )


class _ConformingDurableOperationRecovery:
    def record_attempt(
        self, operation_id: str, expected_revision: OperationRevision, outcome: RedactedEvidence
    ) -> DurableOperationRecord:
        return DurableOperationRecord(
            identity=_identity(),
            revision=OperationRevision(value=expected_revision.value + 1),
            lifecycle=LifecycleState.RECONCILIATION_REQUIRED,
            recovery_evidence=(outcome,),
        )


def test_store_protocol_requires_atomic_lifecycle_operations() -> None:
    store = _ConformingDurableOperationStore()

    assert isinstance(store, DurableOperationStore)
    assert store.create_or_load(_identity()).revision == OperationRevision(value=0)
    assert (
        store.save_checkpoint("operation-42", OperationRevision(value=0), _checkpoint()).checkpoint
        == _checkpoint()
    )
    assert (
        store.commit_terminal("operation-42", _terminal_bundle()).terminal_commit
        == _terminal_bundle()
    )


def test_store_contract_exposes_replay_checkpoint_cas_residual_and_recovery_queries() -> None:
    expected = {
        "create_or_load": ["self", "identity"],
        "save_checkpoint": ["self", "operation_id", "expected_revision", "checkpoint"],
        "mark_reconciliation_required": ["self", "operation_id", "expected_revision"],
        "commit_terminal": ["self", "operation_id", "bundle"],
        "resolve_residual": ["self", "operation_id", "expected_revision"],
        "list_recoverable": ["self"],
    }

    for name, parameters in expected.items():
        assert (
            list(inspect.signature(getattr(DurableOperationStore, name)).parameters) == parameters
        )


def test_losing_concurrent_compare_and_swap_raises_a_typed_revision_conflict() -> None:
    store = _ConformingDurableOperationStore(current_revision=OperationRevision(value=2))

    winner = store.save_checkpoint("operation-42", OperationRevision(value=2), _checkpoint(2))

    with pytest.raises(RevisionConflictError) as loser:
        store.save_checkpoint("operation-42", OperationRevision(value=1), _checkpoint())

    assert winner.revision == OperationRevision(value=3)
    assert loser.value.operation_id == "operation-42"
    assert loser.value.expected_revision == OperationRevision(value=1)
    assert loser.value.actual_revision == OperationRevision(value=2)


def test_terminal_commit_compare_and_swap_rejects_a_stale_revision() -> None:
    store = _ConformingDurableOperationStore(current_revision=OperationRevision(value=5))

    with pytest.raises(RevisionConflictError):
        store.commit_terminal("operation-42", _terminal_bundle())


def test_record_keeps_checkpoint_and_terminal_visibility_distinct() -> None:
    recoverable = _ConformingDurableOperationStore().list_recoverable()
    terminal = _ConformingDurableOperationStore().commit_terminal(
        "operation-42", _terminal_bundle()
    )

    assert recoverable[0].checkpoint == _checkpoint(2)
    assert recoverable[0].terminal_commit is None
    assert terminal.lifecycle is LifecycleState.SUCCEEDED
    assert terminal.terminal_commit == _terminal_bundle()


def test_terminal_commit_with_residual_cleanup_surfaces_cleanup_required_lifecycle() -> None:
    residual = RedactedEvidence(event="cleanup-failed", summary="volume cleanup deferred")

    terminal = _ConformingDurableOperationStore().commit_terminal(
        "operation-42",
        _terminal_bundle(residual_cleanup=(residual,)),
    )

    assert terminal.lifecycle is LifecycleState.CLEANUP_REQUIRED
    assert terminal.terminal_commit is not None
    assert terminal.terminal_commit.outcome is LifecycleState.SUCCEEDED
    assert terminal.terminal_commit.residual_cleanup == (residual,)


def test_recovery_port_records_redacted_workflow_outcomes() -> None:
    recovery = _ConformingDurableOperationRecovery()
    evidence = RedactedEvidence(event="reconciled", summary="provider status reconciled")

    assert isinstance(recovery, DurableOperationRecovery)
    assert recovery.record_attempt(
        "operation-42", OperationRevision(value=2), evidence
    ).recovery_evidence == (evidence,)


def test_nonconforming_store_is_rejected() -> None:
    class _MissingTerminalCommit:
        def create_or_load(self, identity: DurableOperationIdentity) -> DurableOperationRecord:
            return DurableOperationRecord(identity=identity, revision=OperationRevision(value=0))

    assert not isinstance(_MissingTerminalCommit(), DurableOperationStore)


def test_recovery_port_requires_revision_bound_attempts() -> None:
    signature = inspect.signature(DurableOperationRecovery.record_attempt)

    assert list(signature.parameters) == ["self", "operation_id", "expected_revision", "outcome"]
    assert signature.parameters["expected_revision"].default is inspect.Parameter.empty


def test_new_record_is_accepted_and_has_no_authoritative_terminal_commit() -> None:
    record = DurableOperationRecord(identity=_identity(), revision=OperationRevision(value=0))

    assert record.lifecycle is LifecycleState.ACCEPTED
    assert record.checkpoint is None
    assert record.terminal_commit is None
    assert record.recovery_evidence == ()


def test_record_rejects_terminal_outcome_lifecycle_when_residual_cleanup_exists() -> None:
    residual = RedactedEvidence(event="cleanup-failed", summary="volume cleanup deferred")

    with pytest.raises(ValueError, match="cleanup_required lifecycle"):
        DurableOperationRecord(
            identity=_identity(),
            revision=OperationRevision(value=3),
            lifecycle=LifecycleState.SUCCEEDED,
            terminal_commit=_terminal_bundle(residual_cleanup=(residual,)),
        )


def test_record_accepts_cleanup_required_lifecycle_for_residual_terminal_commit() -> None:
    residual = RedactedEvidence(event="cleanup-failed", summary="volume cleanup deferred")

    record = DurableOperationRecord(
        identity=_identity(),
        revision=OperationRevision(value=3),
        lifecycle=LifecycleState.CLEANUP_REQUIRED,
        terminal_commit=_terminal_bundle(residual_cleanup=(residual,)),
    )

    assert record.lifecycle is LifecycleState.CLEANUP_REQUIRED
    assert record.terminal_commit is not None
    assert record.terminal_commit.outcome is LifecycleState.SUCCEEDED


@pytest.mark.parametrize("lifecycle", [LifecycleState.IN_PROGRESS, LifecycleState.CLEANUP_REQUIRED])
def test_recoverable_records_preserve_nonterminal_lifecycle(lifecycle: LifecycleState) -> None:
    record = DurableOperationRecord(
        identity=_identity(), revision=OperationRevision(value=1), lifecycle=lifecycle
    )

    assert record.lifecycle is lifecycle
    assert record.terminal_commit is None
