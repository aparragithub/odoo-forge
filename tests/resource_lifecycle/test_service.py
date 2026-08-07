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
        self.cleanup_reports: list[CleanupReport] = [CleanupReport()]
        self.observations = list(observations) or [
            (DatabaseObservation(ref=_database_ref(), scope=SCOPE, evidence_digest="digest-1"),)
        ]

    def observe(self, scope: ProjectScope) -> tuple[DatabaseObservation, ...]:
        return self.observations.pop(0) if len(self.observations) > 1 else self.observations[0]

    def quarantine(self, ref: DatabaseRef) -> DatabaseRef:
        self.calls.append("quarantine")
        return ref

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        self.calls.append("adopt")
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
        return (
            self.cleanup_reports.pop(0)
            if len(self.cleanup_reports) > 1
            else self.cleanup_reports[0]
        )


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


SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
POINTER = InstancePointer(scope=SCOPE, instance_id=InstanceId(value="db-1"))
RECEIPT = OwnershipReceipt(operation=DurableOperationIdentity(operation_id="operation-1", request_digest="digest-1"), owned_resource_ids=("database-1",))  # fmt: skip  # noqa: E501
RECORD = InstanceRecord(pointer=POINTER, resource=ResourceRef(identifier="database-1", resource_kind="database", ownership=ResourceOwnership.CREATED), receipt=RECEIPT)  # fmt: skip  # noqa: E501
POLICY = LifecyclePolicy(ttl=timedelta(days=7), grace=timedelta(days=1))
AUTHORIZATION = LifecycleAuthorization(actor="operator-1", reason="approved recovery")


def _observation(identifier: str = "database-1", digest: str = "digest-1", *, valid: bool = True, resource_class: ResourceClass = ResourceClass.DEV, last_activity: datetime = NOW - timedelta(days=10), receipt: OwnershipReceipt | None = RECEIPT) -> DatabaseObservation:  # fmt: skip  # noqa: E501
    return DatabaseObservation(ref=DatabaseRef(identifier=identifier, ownership=ResourceOwnership.CREATED), scope=SCOPE, evidence_digest=digest, ownership_valid=valid, resource_class=resource_class, last_activity=last_activity, receipt=receipt)  # fmt: skip  # noqa: E501


# fmt: off
class _Registry:
    def __init__(self, records: tuple[InstanceRecord, ...]): self.records = records  # fmt: skip  # noqa: E501,E701
    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]: return self.records  # fmt: skip  # noqa: E501,E701
    def get(self, pointer: InstancePointer) -> InstanceRecord: return self.records[0]  # fmt: skip  # noqa: E501,E701
# fmt: on


def _service(registry: _Registry, gateway: _ProviderOnlyGateway, journal: LifecycleJournal, retries: int = 2) -> LifecycleService:  # fmt: skip  # noqa: E501
    return LifecycleService(registry=cast(InstanceRegistry, registry), gateway=gateway, journal=journal, max_cleanup_retries=retries)  # fmt: skip  # noqa: E501


def _run(registry: _Registry, gateway: _ProviderOnlyGateway, *, journal: LifecycleJournal | None = None, authorization: LifecycleAuthorization = AUTHORIZATION, delete: bool = False, wait: timedelta = timedelta(), now: datetime | None = None) -> RecoveryResult:  # fmt: skip  # noqa: E501
    return _service(registry, gateway, journal or _AppendOnlyJournal()).run(SCOPE, POLICY, authorization, delete=delete, wait=wait, now=now)[0]  # fmt: skip  # noqa: E501


@pytest.mark.parametrize(
    ("records", "observations", "outcome", "calls"),
    [
        ((RECORD,), ((_observation(),),), RecoveryOutcome.QUARANTINED, ["quarantine"]),
        ((), ((_observation(),),), RecoveryOutcome.ADOPTED, ["quarantine", "adopt"]),
        ((RECORD,), ((),), RecoveryOutcome.RECONCILED, ["reconcile"]),
    ],
)
def test_registry_provider_outcomes(
    records: tuple[InstanceRecord, ...],
    observations: tuple[tuple[DatabaseObservation, ...], ...],
    outcome: RecoveryOutcome,
    calls: list[str],
) -> None:
    gateway = _ProviderOnlyGateway(*observations)
    result = _run(_Registry(records), gateway)
    assert result.outcome is outcome
    assert gateway.calls == calls


@pytest.mark.parametrize(
    ("reobservation", "code"),
    [
        ((_observation(digest="digest-2"),), "evidence-drift"),
        ((_observation(valid=False),), "invalid-ownership"),
    ],
)
def test_digest_drift_or_ownership_contradiction_fails_closed_without_mutation(
    reobservation: tuple[DatabaseObservation, ...], code: str
) -> None:
    gateway = _ProviderOnlyGateway((_observation(),), reobservation)
    result = _run(_Registry((RECORD,)), gateway)
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION
    assert gateway.calls == [] and result.residuals[0].code == code


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
def test_cleanup_retries_are_bounded_and_escalate(
    reports: list[CleanupReport], outcome: RecoveryOutcome, code: str | None
) -> None:
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
    result = _run(
        _Registry((RECORD,)),
        gateway,
        authorization=AUTHORIZATION.model_copy(update={"approved": False}),
    )
    assert result.outcome is RecoveryOutcome.HUMAN_INTERVENTION and gateway.calls == []


@pytest.mark.parametrize(
    ("records", "observations"),
    [((RECORD, RECORD), (_observation(),)), ((RECORD,), (_observation(), _observation()))],
)
def test_duplicate_evidence_is_contradictory_without_mutation(
    records: tuple[InstanceRecord, ...], observations: tuple[DatabaseObservation, ...]
) -> None:
    gateway = _ProviderOnlyGateway(observations)
    result = _service(_Registry(records), gateway, _AppendOnlyJournal()).run(
        SCOPE, POLICY, AUTHORIZATION
    )
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
