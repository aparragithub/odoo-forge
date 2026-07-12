import pytest

from odoo_forge.durable_operations import (
    CompensationScope,
    DurableOperationIdentity,
    IncompleteTerminalCommitError,
    InvalidLifecycleTransitionError,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
    ReplayConflictError,
    UnsafeCompensationError,
)
from odoo_forge.durable_operations.service import (
    RecoveryAction,
    advance_lifecycle,
    build_terminal_commit,
    ensure_compensation_target,
    plan_recovery,
    replay_or_conflict,
    save_checkpoint,
)


def test_same_identity_and_request_digest_replays_the_recorded_operation() -> None:
    recorded = DurableOperationIdentity(
        operation_id="operation-42", request_digest="sha256-request-42"
    )

    replayed = replay_or_conflict(recorded, "sha256-request-42")

    assert replayed is recorded


def test_mismatched_request_digest_preserves_the_recorded_identity_and_rejects_replay() -> None:
    recorded = DurableOperationIdentity(
        operation_id="operation-42", request_digest="sha256-request-42"
    )

    with pytest.raises(ReplayConflictError):
        replay_or_conflict(recorded, "sha256-request-99")

    assert recorded.request_digest == "sha256-request-42"


def test_lifecycle_progression_is_forward_only_and_increments_revision() -> None:
    state, revision = advance_lifecycle(
        LifecycleState.ACCEPTED,
        OperationRevision(value=2),
        LifecycleState.IN_PROGRESS,
    )

    assert state is LifecycleState.IN_PROGRESS
    assert revision == OperationRevision(value=3)
    with pytest.raises(InvalidLifecycleTransitionError):
        advance_lifecycle(state, revision, LifecycleState.ACCEPTED)


def test_lifecycle_allows_same_or_later_states_but_never_reuses_the_revision() -> None:
    state, revision = advance_lifecycle(
        LifecycleState.IN_PROGRESS,
        OperationRevision(value=3),
        LifecycleState.IN_PROGRESS,
    )

    assert state is LifecycleState.IN_PROGRESS
    assert revision == OperationRevision(value=4)


def test_lifecycle_rejects_flipping_a_published_terminal_outcome() -> None:
    with pytest.raises(InvalidLifecycleTransitionError):
        advance_lifecycle(
            LifecycleState.SUCCEEDED,
            OperationRevision(value=4),
            LifecycleState.FAILED,
        )

    with pytest.raises(InvalidLifecycleTransitionError):
        advance_lifecycle(
            LifecycleState.FAILED,
            OperationRevision(value=4),
            LifecycleState.SUCCEEDED,
        )


def test_lifecycle_keeps_terminal_outcomes_re_advanceable_towards_cleanup_and_closure() -> None:
    same_outcome, same_revision = advance_lifecycle(
        LifecycleState.SUCCEEDED,
        OperationRevision(value=4),
        LifecycleState.SUCCEEDED,
    )
    cleanup, cleanup_revision = advance_lifecycle(
        LifecycleState.FAILED,
        OperationRevision(value=4),
        LifecycleState.CLEANUP_REQUIRED,
    )

    assert same_outcome is LifecycleState.SUCCEEDED
    assert same_revision == OperationRevision(value=5)
    assert cleanup is LifecycleState.CLEANUP_REQUIRED
    assert cleanup_revision == OperationRevision(value=5)


def test_checkpoint_records_resume_safe_progress_for_recovery() -> None:
    checkpoint = save_checkpoint(
        revision=OperationRevision(value=2),
        phase="provider-mutation-complete",
        evidence=RedactedEvidence(
            event="checkpoint-recorded", summary="provider receipt captured"
        ),
    )

    plan = plan_recovery(
        LifecycleState.IN_PROGRESS,
        OperationRevision(value=2),
        checkpoint,
        mutation_attempted=True,
    )

    assert plan.action is RecoveryAction.RESUME
    assert plan.checkpoint is checkpoint
    assert plan.revision == OperationRevision(value=3)


def test_checkpoint_requires_a_resume_safe_phase() -> None:
    with pytest.raises(ValueError, match="phase"):
        save_checkpoint(
            revision=OperationRevision(value=2),
            phase="",
            evidence=RedactedEvidence(event="checkpoint-recorded", summary="safe evidence"),
        )


def test_unknown_progress_requires_reconciliation_instead_of_repeating_mutation() -> None:
    plan = plan_recovery(
        LifecycleState.IN_PROGRESS,
        OperationRevision(value=7),
        None,
        mutation_attempted=True,
    )

    assert plan.action is RecoveryAction.RECONCILE
    assert plan.revision == OperationRevision(value=7)
    assert plan.reason == "mutation outcome is unknown without a durable checkpoint"


def test_recovery_without_a_mutation_starts_from_a_fresh_resumable_state() -> None:
    plan = plan_recovery(
        LifecycleState.ACCEPTED,
        OperationRevision(value=0),
        None,
        mutation_attempted=False,
    )

    assert plan.action is RecoveryAction.RESUME
    assert plan.revision == OperationRevision(value=0)
    assert plan.reason == "no mutation has been attempted"


def test_cleanup_required_recovery_surfaces_residual_work_without_provider_decision() -> None:
    plan = plan_recovery(
        LifecycleState.CLEANUP_REQUIRED,
        OperationRevision(value=4),
        None,
        mutation_attempted=False,
    )

    assert plan.action is RecoveryAction.SURFACE_RESIDUAL
    assert plan.revision == OperationRevision(value=4)
    assert plan.reason == "residual cleanup remains open"


def test_reconciliation_required_recovery_never_resumes_even_with_checkpoint() -> None:
    checkpoint = save_checkpoint(
        revision=OperationRevision(value=4),
        phase="provider-mutation-complete",
        evidence=RedactedEvidence(
            event="checkpoint-recorded", summary="provider receipt captured"
        ),
    )

    plan = plan_recovery(
        LifecycleState.RECONCILIATION_REQUIRED,
        OperationRevision(value=5),
        checkpoint,
        mutation_attempted=True,
    )

    assert plan.action is RecoveryAction.RECONCILE
    assert plan.revision == OperationRevision(value=5)
    assert plan.checkpoint is checkpoint
    assert plan.reason == "mutation outcome requires reconciliation"


def test_terminal_bundle_contains_outcome_evidence_and_residual_cleanup_together() -> None:
    residual = RedactedEvidence(event="cleanup-failed", summary="volume cleanup deferred")

    bundle = build_terminal_commit(
        expected_revision=OperationRevision(value=3),
        outcome=LifecycleState.SUCCEEDED,
        evidence=(RedactedEvidence(event="terminal", summary="database created"),),
        residual_cleanup=(residual,),
    )

    assert bundle.outcome is LifecycleState.SUCCEEDED
    assert bundle.evidence[0].event == "terminal"
    assert bundle.residual_cleanup == (residual,)


def test_terminal_bundle_rejects_non_terminal_lifecycle_states() -> None:
    with pytest.raises(IncompleteTerminalCommitError, match="outcome"):
        build_terminal_commit(
            expected_revision=OperationRevision(value=3),
            outcome=LifecycleState.TERMINAL_PENDING,
            evidence=(RedactedEvidence(event="terminal", summary="pending"),),
            residual_cleanup=(),
        )


def test_terminal_bundle_rejects_partial_authoritative_publication() -> None:
    with pytest.raises(IncompleteTerminalCommitError, match="evidence"):
        build_terminal_commit(
            expected_revision=OperationRevision(value=3),
            outcome=LifecycleState.FAILED,
            evidence=(),
            residual_cleanup=(),
        )


def test_compensation_targets_only_invocation_owned_resources() -> None:
    scope = CompensationScope(
        operation_id="operation-42", owned_resource_ids=("database-42",)
    )

    assert ensure_compensation_target(scope, "database-42") == "database-42"
    with pytest.raises(UnsafeCompensationError):
        ensure_compensation_target(scope, "database-99")
