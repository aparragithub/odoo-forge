from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from odoo_forge.database import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    OperationIdentity,
    ResourceOwnership,
)
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.errors import InstanceRecordNotFoundError
from odoo_forge.instance_registry.types import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.ports.resource_lifecycle import (
    DatabaseLifecycleGateway,
    LifecycleAlertSink,
    LifecycleJournal,
    LifecycleSchedulerGate,
)
from odoo_forge.resource_lifecycle.service import (
    LifecycleService,
    RecoveryOutcome,
    RecoveryResult,
)
from odoo_forge.resource_lifecycle.types import (
    DatabaseObservation,
    ExpirationAction,
    LifecycleAuthorization,
    LifecycleEvidence,
    LifecycleJournalEvent,
    LifecycleOutcome,
    LifecyclePolicy,
    LifecycleResidual,
    LifecycleResource,
    ProviderPresence,
    QuarantineHistory,
    ResourceClass,
    ResourceOverride,
    evaluate_expiration,
    reset_activity_baseline,
)
from odoo_forge.resource_ownership.types import OwnershipReceipt, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId

NOW = datetime(2026, 1, 10, tzinfo=UTC)


def test_policy_accepts_only_approved_classes_and_applies_resource_override() -> None:
    policy = LifecyclePolicy(
        ttl=timedelta(days=7),
        grace=timedelta(days=2),
        approved_classes=frozenset({ResourceClass.DEV, ResourceClass.QA}),
        overrides=(ResourceOverride(resource_id="qa-1", ttl=timedelta(days=3)),),
    )

    assert policy.is_approved(ResourceClass.DEV)
    assert policy.is_approved(ResourceClass.QA)
    assert not policy.is_approved(ResourceClass.PROD)
    assert policy.ttl_for("qa-1") == timedelta(days=3)
    assert policy.ttl_for("dev-1") == timedelta(days=7)


def test_qualifying_activity_resets_ttl_plus_grace_baseline() -> None:
    resource = LifecycleResource(
        resource_id="dev-1",
        resource_class=ResourceClass.DEV,
        last_activity=NOW - timedelta(days=10),
    )
    policy = LifecyclePolicy(ttl=timedelta(days=7), grace=timedelta(days=2))

    assert evaluate_expiration(resource, NOW, policy).action is ExpirationAction.EXPIRE

    renewed = reset_activity_baseline(resource, NOW)

    assert renewed.last_activity == NOW
    assert evaluate_expiration(renewed, NOW, policy).eligible is False


def test_prod_is_alert_and_audit_only_even_after_ttl_and_grace() -> None:
    resource = LifecycleResource(
        resource_id="prod-1",
        resource_class=ResourceClass.PROD,
        last_activity=NOW - timedelta(days=100),
    )
    policy = LifecyclePolicy(
        ttl=timedelta(days=7),
        grace=timedelta(days=2),
        approved_classes=frozenset({ResourceClass.DEV, ResourceClass.QA, ResourceClass.PROD}),
    )

    decision = evaluate_expiration(resource, NOW, policy)

    assert decision.action is ExpirationAction.ALERT_AUDIT_ONLY
    assert decision.eligible is False
    assert decision.mutation_allowed is False


class _Alerts:
    def alert(self, resource: LifecycleResource, decision: object) -> None:
        return None


class _Scheduler:
    def enabled(self) -> bool:
        return False


def test_alert_and_scheduler_ports_are_small_independent_runtime_contracts() -> None:
    assert isinstance(_Alerts(), LifecycleAlertSink)
    assert isinstance(_Scheduler(), LifecycleSchedulerGate)
    assert _Scheduler().enabled() is False


class _AppendOnlyJournal:
    def __init__(self) -> None:
        self._events: list[LifecycleJournalEvent] = []

    def append(self, event: LifecycleJournalEvent) -> LifecycleJournalEvent:
        self._events.append(event)
        return event

    def events(self) -> tuple[LifecycleJournalEvent, ...]:
        return tuple(self._events)


def test_journal_appends_the_complete_immutable_audit_payload() -> None:
    event = LifecycleJournalEvent(
        policy=LifecyclePolicy(ttl=timedelta(days=7), grace=timedelta(days=2)),
        evidence=LifecycleEvidence(source="registry", digest="evidence-1"),
        authorization=LifecycleAuthorization(actor="operator-1", reason="approved"),
        outcome=LifecycleOutcome.EXPIRED,
        residuals=(LifecycleResidual(code="none", detail="no residuals"),),
    )
    journal = _AppendOnlyJournal()

    assert isinstance(journal, LifecycleJournal)
    appended = journal.append(event)

    assert appended == event
    assert journal.events() == (event,)
    assert event.policy.ttl == timedelta(days=7)
    assert event.evidence.digest == "evidence-1"
    assert event.authorization.actor == "operator-1"
    assert event.outcome is LifecycleOutcome.EXPIRED
    assert event.residuals[0].code == "none"


def test_journal_snapshot_and_payload_cannot_be_mutated_after_append() -> None:
    event = LifecycleJournalEvent(
        policy=LifecyclePolicy(ttl=timedelta(days=1), grace=timedelta(hours=1)),
        evidence=LifecycleEvidence(source="provider", digest="evidence-2"),
        authorization=LifecycleAuthorization(actor="operator-2", reason="reviewed"),
        outcome=LifecycleOutcome.ALERTED,
    )
    journal = _AppendOnlyJournal()
    journal.append(event)

    with pytest.raises((TypeError, ValueError)):
        event.policy.ttl = timedelta(days=2)  # type: ignore[misc]
    with pytest.raises((TypeError, ValueError)):
        journal.events()[0].residuals += (LifecycleResidual(code="late", detail="changed"),)  # type: ignore[misc]

    assert journal.events() == (event,)


def _database_ref() -> DatabaseRef:
    return DatabaseRef(identifier="database-1", ownership=ResourceOwnership.CREATED)


class _ProviderOnlyGateway:
    def __init__(self, *observations: tuple[DatabaseObservation, ...]) -> None:
        self.calls: list[str] = []
        self.adopted_ref: DatabaseRef | None = None
        self.quarantined_ref: DatabaseRef | None = None
        self.cleanup_reports: list[CleanupReport] = [CleanupReport()]
        self.observations = list(observations) or [(DatabaseObservation(ref=_database_ref(), scope=SCOPE, evidence_digest="digest-1"),)]  # fmt: skip  # noqa: E501

    def observe(self, scope: ProjectScope) -> tuple[DatabaseObservation, ...]:
        return self.observations.pop(0) if len(self.observations) > 1 else self.observations[0]

    def quarantine(self, ref: DatabaseRef) -> DatabaseRef:
        self.calls.append("quarantine")
        return self.quarantined_ref or ref

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        self.calls.append("adopt")
        self.adopted_ref = ref
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        self.calls.append("reconcile")
        return DatabaseCreation(
            ref=_database_ref(),
            receipt=CreationReceipt(operation=operation, owned_resource_ids=("database-1",)),
        )

    def delete(self, creation: DatabaseCreation) -> None: self.calls.append("delete")  # fmt: skip  # noqa: E501,E701

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        self.calls.append("cleanup")
        return self.cleanup_reports.pop(0) if len(self.cleanup_reports) > 1 else self.cleanup_reports[0]  # fmt: skip  # noqa: E501


def test_gateway_is_provider_only_and_keeps_registry_out_of_the_port() -> None:
    gateway = _ProviderOnlyGateway()

    assert isinstance(gateway, DatabaseLifecycleGateway)
    assert not hasattr(DatabaseLifecycleGateway, "store")
    assert not hasattr(DatabaseLifecycleGateway, "list")
    assert not hasattr(DatabaseLifecycleGateway, "provision")
    assert not hasattr(DatabaseLifecycleGateway, "restore")


def test_gateway_exposes_observation_and_typed_provider_lifecycle_verbs() -> None:
    gateway = _ProviderOnlyGateway()
    operation = OperationIdentity(value="operation-1")
    ref = _database_ref()
    creation = gateway.reconcile(operation)
    scope = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")

    assert gateway.observe(scope)[0].ref == ref
    assert gateway.quarantine(ref) == ref
    assert gateway.adopt(ref) == ref
    assert creation.receipt.operation == operation
    assert gateway.cleanup(creation.receipt) == CleanupReport()


# fmt: off
SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
POINTER = InstancePointer(scope=SCOPE, instance_id=InstanceId(value="db-1"))
RECEIPT = OwnershipReceipt(operation=DurableOperationIdentity(operation_id="operation-1", request_digest="digest-1"), owned_resource_ids=("database-1",))  # fmt: skip  # noqa: E501
RECORD = InstanceRecord(pointer=POINTER, resource=ResourceRef(identifier="database-1", resource_kind="database", ownership=ResourceOwnership.CREATED), receipt=RECEIPT)  # fmt: skip  # noqa: E501
POLICY = LifecyclePolicy(ttl=timedelta(days=7), grace=timedelta(days=1))
AUTHORIZATION = LifecycleAuthorization(actor="operator-1", reason="approved recovery")
OTHER_SCOPE = ProjectScope(tenant=TenantId(value="other"), project_id="project-1")
OTHER_OPERATION = DurableOperationIdentity(operation_id="other", request_digest="other")


def _observation(identifier: str = "database-1", digest: str = "digest-1", *, scope: ProjectScope = SCOPE, valid: bool = True, resource_class: ResourceClass = ResourceClass.DEV, last_activity: datetime = NOW - timedelta(days=10), receipt: OwnershipReceipt | None = RECEIPT, presence: ProviderPresence = ProviderPresence.PRESENT) -> DatabaseObservation:  # fmt: skip  # noqa: E501
    return DatabaseObservation(ref=DatabaseRef(identifier=identifier, ownership=ResourceOwnership.CREATED), scope=scope, evidence_digest=digest, ownership_valid=valid, resource_class=resource_class, last_activity=last_activity, receipt=receipt, presence=presence)  # fmt: skip  # noqa: E501


class _Registry:
    def __init__(self, records: tuple[InstanceRecord, ...], *current: InstanceRecord | None): self.records, self.current = records, list(current) or list(records)  # fmt: skip  # noqa: E501,E701
    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]: return self.records  # fmt: skip  # noqa: E501,E701
    def get(self, pointer: InstancePointer) -> InstanceRecord:
        current = self.current.pop(0) if self.current else (self.records[0] if self.records else None)  # noqa: E501
        if current is None: raise InstanceRecordNotFoundError(pointer)  # fmt: skip  # noqa: E701
        return current
def _service(registry: "_Registry | _HistoryRegistry", gateway: _ProviderOnlyGateway, journal: LifecycleJournal, retries: int = 2) -> LifecycleService:  # fmt: skip  # noqa: E501
    return LifecycleService(registry=cast(InstanceRegistry, registry), gateway=gateway, journal=journal, max_cleanup_retries=retries)  # fmt: skip  # noqa: E501


def _run(registry: _Registry, gateway: _ProviderOnlyGateway, *, journal: LifecycleJournal | None = None, authorization: LifecycleAuthorization = AUTHORIZATION, delete: bool = False, wait: timedelta = timedelta(), now: datetime | None = None) -> RecoveryResult:  # fmt: skip  # noqa: E501
    return _service(registry, gateway, journal or _AppendOnlyJournal()).run(SCOPE, POLICY, authorization, delete=delete, wait=wait, now=now)[0]  # fmt: skip  # noqa: E501


def _history() -> QuarantineHistory:
    return QuarantineHistory(
        pointer=POINTER,
        scope=SCOPE,
        resource=_database_ref(),
        operation=RECEIPT.operation,
        evidence_digest="digest-1",
        resource_class=ResourceClass.DEV,
        quarantined_at=NOW - timedelta(days=2),
    )


def _history_journal(history: QuarantineHistory | None = None) -> _AppendOnlyJournal:
    journal = _AppendOnlyJournal()
    journal.append(
        LifecycleJournalEvent(
            policy=POLICY,
            evidence=LifecycleEvidence(source="lifecycle", digest="digest-1"),
            authorization=AUTHORIZATION,
            outcome=RecoveryOutcome.QUARANTINED,
            history=history or _history(),
        )
    )
    return journal


@pytest.mark.parametrize(
    ("records", "observations", "outcome", "calls"),
    [
        ((RECORD,), ((_observation(),),), RecoveryOutcome.QUARANTINED, ["quarantine"]),
        ((), ((_observation(),),), RecoveryOutcome.ADOPTED, ["quarantine", "adopt"]),
        ((RECORD,), ((),), RecoveryOutcome.RECONCILED, ["reconcile"]),
    ],
)
def test_registry_provider_outcomes(  # fmt: skip
    records: tuple[InstanceRecord, ...], observations: tuple[tuple[DatabaseObservation, ...], ...], outcome: RecoveryOutcome, calls: list[str]  # fmt: skip  # noqa: E501
) -> None:
    gateway = _ProviderOnlyGateway(*observations)
    result = _run(_Registry(records), gateway)
    assert result.outcome is outcome
    assert gateway.calls == calls


@pytest.mark.parametrize(  # fmt: skip
    ("reobservation", "code"),
    [
        ((_observation(digest="digest-2"),), "evidence-drift"),
        ((_observation(valid=False),), "invalid-ownership"),
        ((_observation(scope=ProjectScope(tenant=TenantId(value="tenant-2"), project_id="project-1")),), "scope-mismatch"),  # noqa: E501
        ((_observation(last_activity=NOW - timedelta(days=7)),), "ineligible"),
        ((_observation(receipt=RECEIPT.model_copy(update={"operation": DurableOperationIdentity(operation_id="other-operation", request_digest="digest-1")})),), "lineage-mismatch"),  # noqa: E501
    ],
)
def test_revalidation_contradiction_fails_closed_without_mutation(
    reobservation: tuple[DatabaseObservation, ...], code: str
) -> None:
    gateway = _ProviderOnlyGateway((_observation(),), reobservation)
    result = _run(_Registry((RECORD,)), gateway, now=NOW)
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert gateway.calls == [] and result.residuals[0].code == code


def test_adoption_uses_ref_returned_by_quarantine() -> None:
    gateway = _ProviderOnlyGateway((_observation(),))
    gateway.quarantined_ref = DatabaseRef(identifier="quarantined", ownership=ResourceOwnership.CREATED)  # fmt: skip  # noqa: E501
    result = _run(_Registry(()), gateway)
    assert result.outcome is RecoveryOutcome.ADOPTED and gateway.adopted_ref == gateway.quarantined_ref  # fmt: skip  # noqa: E501


@pytest.mark.parametrize("delete,current", [(True, None), (True, RECORD.model_copy(update={"receipt": None})), (False, None), (False, RECORD.model_copy(update={"receipt": None}))])  # fmt: skip  # noqa: E501
def test_registry_drift_or_removal_prevents_mutation(delete: bool, current: InstanceRecord | None) -> None:  # fmt: skip  # noqa: E501
    gateway = _ProviderOnlyGateway((_observation(),) if delete else ())
    result = _run(_Registry((RECORD,), *(RECORD, current) if delete else (current,)), gateway, delete=delete)  # noqa: E501
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION and gateway.calls == (["quarantine"] if delete else [])  # fmt: skip  # noqa: E501


@pytest.mark.parametrize(
    ("reports", "outcome", "code"),
    [
        (
            [CleanupReport(residual_failures=("network",)), CleanupReport()],
            RecoveryOutcome.DELETED,
            None,
        ),
        (
            [CleanupReport(residual_failures=("network",))],
            RecoveryOutcome.HUMAN_INTERVENTION,
            "partial-cleanup",
        ),
    ],
)
def test_cleanup_retries_are_bounded_and_escalate(reports: list[CleanupReport], outcome: RecoveryOutcome, code: str | None) -> None:  # fmt: skip  # noqa: E501
    gateway = _ProviderOnlyGateway((_observation(),))
    gateway.cleanup_reports = reports
    result = _run(_Registry((RECORD,)), gateway, delete=True)
    assert result.outcome is outcome
    if code:
        assert result.residuals[0].code == code
    assert gateway.calls.count("cleanup") == (2 if outcome is RecoveryOutcome.DELETED else 3)


def test_deletion_cancellation_appends_changed_evidence_and_makes_no_delete_call() -> None:
    gateway = _ProviderOnlyGateway(
        (_observation(),), (_observation(),), (_observation(digest="digest-2"),)
    )
    journal = _AppendOnlyJournal()
    result = _run(_Registry((RECORD,)), gateway, journal=journal, delete=True)
    assert result.outcome is RecoveryOutcome.CANCELLED and result.residuals[0].code == "evidence-changed" and gateway.calls == ["quarantine"]  # fmt: skip  # noqa: E501
    assert journal.events()[-1].evidence.digest == "digest-2"


def test_unapproved_authorization_has_zero_mutation_calls() -> None:
    gateway = _ProviderOnlyGateway((_observation(),))
    result = _run(_Registry((RECORD,)), gateway, authorization=AUTHORIZATION.model_copy(update={"approved": False}))  # fmt: skip  # noqa: E501
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION and gateway.calls == []


@pytest.mark.parametrize(
    ("records", "observations"),
    [((RECORD, RECORD), (_observation(),)), ((RECORD,), (_observation(), _observation()))],
)
def test_duplicate_evidence_is_contradictory_without_mutation(  # fmt: skip
    records: tuple[InstanceRecord, ...], observations: tuple[DatabaseObservation, ...]  # fmt: skip  # noqa: E501
) -> None:
    gateway = _ProviderOnlyGateway(observations)
    result = _service(_Registry(records), gateway, _AppendOnlyJournal()).run(SCOPE, POLICY, AUTHORIZATION)  # fmt: skip  # noqa: E501
    assert len(result) == 1 and result[0].residuals[0].code == "duplicate-evidence"
    assert result[0].outcome is RecoveryOutcome.HUMAN_INTERVENTION and gateway.calls == []


@pytest.mark.parametrize(
    ("resource_class", "last_activity"),
    [(ResourceClass.DEV, NOW - timedelta(days=7)), (ResourceClass.PROD, NOW - timedelta(days=100))],
)
def test_ineligible_resource_is_not_quarantined(
    resource_class: ResourceClass, last_activity: datetime
) -> None:
    observation = _observation(resource_class=resource_class, last_activity=last_activity)
    gateway = _ProviderOnlyGateway((observation,))
    result = _run(_Registry((RECORD,)), gateway, now=NOW)
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION and result.residuals[0].code == "ineligible" and gateway.calls == []  # fmt: skip  # noqa: E501


def test_operation_receipt_lineage_mismatch_is_contradictory_without_mutation() -> None:
    observation = _observation(
        receipt=RECEIPT.model_copy(
            update={
                "operation": DurableOperationIdentity(
                    operation_id="other-operation", request_digest="digest-1"
                )
            }
        )
    )
    gateway = _ProviderOnlyGateway((observation,))
    result = _run(_Registry((RECORD,)), gateway)
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION and result.residuals[0].code == "lineage-mismatch" and gateway.calls == []  # fmt: skip  # noqa: E501


def test_positive_wait_keeps_resource_quarantined_without_deletion() -> None:
    gateway = _ProviderOnlyGateway((_observation(),))
    result = _run(_Registry((RECORD,)), gateway, delete=True, wait=timedelta(days=1), now=NOW)
    assert result.outcome is RecoveryOutcome.QUARANTINED and result.residuals[0].code == "quarantine-wait" and gateway.calls == ["quarantine"]  # fmt: skip  # noqa: E501
class _HistoryRegistry:
    def __init__(self) -> None:
        self.records = [(RECORD,), ()]
        self.get_results: list[InstanceRecord | None] = [RECORD, None]
        self.get_calls: list[InstancePointer] = []

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        return self.records.pop(0)

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        self.get_calls.append(pointer)
        result = self.get_results.pop(0)
        if result is None:
            raise InstanceRecordNotFoundError(pointer)
        return result


def test_quarantine_history_reuses_exact_pointer_and_preserves_lineage() -> None:
    registry = _HistoryRegistry()
    gateway = _ProviderOnlyGateway((_observation(),), (_observation(),), ())
    journal = _AppendOnlyJournal()
    service = _service(registry, gateway, journal)

    service.run(SCOPE, POLICY, AUTHORIZATION, now=NOW)
    service.run(SCOPE, POLICY, AUTHORIZATION, now=NOW)

    history = journal.events()[1].history
    assert history == QuarantineHistory(
        pointer=POINTER,
        scope=SCOPE,
        resource=_database_ref(),
        operation=RECEIPT.operation,
        evidence_digest="digest-1",
        resource_class=ResourceClass.DEV,
        quarantined_at=NOW,
    )
    assert registry.get_calls[-1] == POINTER


@pytest.mark.parametrize("presence", [ProviderPresence.ABSENT, ProviderPresence.INVALID])
def test_confirmed_zombie_requires_registry_absence_and_provider_absent_or_invalid(
    presence: ProviderPresence,
) -> None:
    journal = _history_journal()
    observations = () if presence is ProviderPresence.ABSENT else (_observation(presence=presence),)
    gateway = _ProviderOnlyGateway(observations)

    result = _service(_Registry(()), gateway, journal).run(SCOPE, POLICY, AUTHORIZATION)[0]

    assert result.outcome is RecoveryOutcome.QUARANTINED
    assert gateway.calls == ["quarantine"]


@pytest.mark.parametrize(
    ("history", "observation"),
    [
        (_history().model_copy(update={"scope": OTHER_SCOPE}), None),
        (
            _history().model_copy(update={"evidence_digest": "other-digest"}),
            _observation(presence=ProviderPresence.INVALID),
        ),
        (
            _history().model_copy(update={"operation": OTHER_OPERATION}),
            _observation(presence=ProviderPresence.INVALID),
        ),
    ],
)
def test_mismatched_history_fails_closed_without_mutation(
    history: QuarantineHistory, observation: DatabaseObservation | None
) -> None:
    journal = _history_journal(history)
    gateway = (
        _ProviderOnlyGateway(())
        if observation is None
        else _ProviderOnlyGateway((observation,))
    )

    result = _service(_Registry(()), gateway, journal).run(SCOPE, POLICY, AUTHORIZATION)[0]

    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert gateway.calls == []


def test_duplicate_history_fails_closed_without_mutation() -> None:
    journal = _history_journal()
    journal.append(journal.events()[0])
    gateway = _ProviderOnlyGateway(())

    result = _service(_Registry(()), gateway, journal).run(SCOPE, POLICY, AUTHORIZATION)[0]

    assert result.residuals[0].code == "duplicate-history"
    assert gateway.calls == []


def test_empty_run_appends_a_run_audit_with_residuals() -> None:
    journal = _AppendOnlyJournal()
    result = _service(_Registry(()), _ProviderOnlyGateway(()), journal).run(
        SCOPE, POLICY, AUTHORIZATION
    )

    assert result == ()
    assert journal.events()[0].kind == "run"
    assert journal.events()[0].residuals[0].code == "empty-run"


def test_confirmed_zombie_delete_revalidates_before_mutating_delete() -> None:
    journal = _history_journal()
    gateway = _ProviderOnlyGateway((), (_observation(presence=ProviderPresence.PRESENT),))

    result = _service(_Registry(()), gateway, journal).run(
        SCOPE, POLICY, AUTHORIZATION, delete=True
    )[0]

    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert result.residuals[0].code == "not-confirmed-zombie"
    assert gateway.calls == ["quarantine"]


@pytest.mark.parametrize(
    "returned",
    [
        RECORD.model_copy(
            update={"resource": ResourceRef(
                identifier="other-database",
                resource_kind="database",
                ownership=ResourceOwnership.CREATED,
            )}
        ),
        RECORD.model_copy(
            update={
                "receipt": RECEIPT.model_copy(
                    update={"operation": DurableOperationIdentity(
                        operation_id="other-operation", request_digest="other-digest"
                    )}
                )
            }
        ),
    ],
)
def test_history_rejects_returned_identity_or_operation_mismatch_without_mutation(
    returned: InstanceRecord,
) -> None:
    journal = _history_journal()
    gateway = _ProviderOnlyGateway(())

    result = _service(_Registry((), returned, returned), gateway, journal).run(
        SCOPE, POLICY, AUTHORIZATION
    )[0]

    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert result.residuals[0].code == "history-mismatch"
    assert gateway.calls == []


def test_prod_history_cannot_be_classified_as_a_zombie() -> None:
    journal = _history_journal(_history().model_copy(update={"resource_class": ResourceClass.PROD}))
    gateway = _ProviderOnlyGateway(())
    policy = POLICY.model_copy(
        update={
            "approved_classes": frozenset(
                {ResourceClass.DEV, ResourceClass.QA, ResourceClass.PROD}
            )
        }
    )

    result = _service(_Registry(()), gateway, journal).run(SCOPE, policy, AUTHORIZATION)[0]

    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert result.residuals[0].code == "not-confirmed-zombie"
    assert gateway.calls == []


def _history_without_quarantine_timestamp() -> QuarantineHistory:
    construct = cast(Callable[..., QuarantineHistory], QuarantineHistory.model_construct)
    return construct(
        pointer=POINTER,
        scope=SCOPE,
        resource=_database_ref(),
        operation=RECEIPT.operation,
        evidence_digest="digest-1",
        resource_class=ResourceClass.DEV,
    )


@pytest.mark.parametrize(
    "history",
    [
        _history().model_copy(update={"quarantined_at": NOW + timedelta(minutes=1)}),
        _history().model_copy(update={"quarantined_at": datetime(2026, 1, 8)}),
        _history_without_quarantine_timestamp(),
    ],
)
def test_history_delete_requires_valid_elapsed_quarantine_timestamp(
    history: QuarantineHistory,
) -> None:
    journal = _history_journal(history)
    gateway = _ProviderOnlyGateway(())

    result = _service(_Registry(()), gateway, journal).run(
        SCOPE,
        POLICY,
        AUTHORIZATION,
        delete=True,
        wait=timedelta(days=1),
        now=NOW,
    )[0]

    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert result.residuals[0].code == "quarantine-wait"
    assert gateway.calls == []


def test_history_delete_requires_elapsed_wait_before_mutating() -> None:
    journal = _history_journal()
    gateway = _ProviderOnlyGateway((), ())

    result = _service(_Registry(()), gateway, journal).run(
        SCOPE,
        POLICY,
        AUTHORIZATION,
        delete=True,
        wait=timedelta(days=1),
        now=NOW,
    )[0]

    assert result.outcome is RecoveryOutcome.DELETED
    assert gateway.calls == ["quarantine", "delete", "cleanup"]


def test_qa_confirmed_zombie_history_requires_concordant_class() -> None:
    qa_history = _history().model_copy(update={"resource_class": ResourceClass.QA})
    journal = _history_journal(qa_history)
    gateway = _ProviderOnlyGateway(
        (_observation(resource_class=ResourceClass.QA, presence=ProviderPresence.INVALID),)
    )

    result = _service(_Registry(()), gateway, journal).run(
        SCOPE, POLICY, AUTHORIZATION
    )[0]

    assert result.outcome is RecoveryOutcome.QUARANTINED
    assert gateway.calls == ["quarantine"]
    history_event = next(event for event in journal.events() if event.history is not None)
    assert history_event.history is not None
    assert history_event.history.resource_class is ResourceClass.QA

    contradictory_gateway = _ProviderOnlyGateway(
        (_observation(resource_class=ResourceClass.DEV, presence=ProviderPresence.INVALID),)
    )
    contradictory_result = _service(
        _Registry(()), contradictory_gateway, _history_journal(qa_history)
    ).run(SCOPE, POLICY, AUTHORIZATION)[0]

    assert contradictory_result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert contradictory_gateway.calls == []


def test_action_audit_contains_each_mutating_action_and_residuals() -> None:
    journal = _AppendOnlyJournal()
    gateway = _ProviderOnlyGateway((_observation(),))
    gateway.cleanup_reports = [CleanupReport(residual_failures=("network",))]

    result = _service(_Registry((RECORD,)), gateway, journal).run(
        SCOPE, POLICY, AUTHORIZATION, delete=True
    )[0]

    actions = [event for event in journal.events() if event.kind == "action"]
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert [event.outcome for event in actions] == [
        RecoveryOutcome.QUARANTINED,
        RecoveryOutcome.DELETED,
        RecoveryOutcome.HUMAN_INTERVENTION,
    ]
    assert actions[-1].residuals[0].detail == "network"
# fmt: on
