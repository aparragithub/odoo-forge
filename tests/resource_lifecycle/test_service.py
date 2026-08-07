from datetime import UTC, datetime, timedelta

import pytest

from odoo_forge.database import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    OperationIdentity,
    ResourceOwnership,
)
from odoo_forge.ports.resource_lifecycle import (
    DatabaseLifecycleGateway,
    LifecycleAlertSink,
    LifecycleJournal,
    LifecycleSchedulerGate,
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
    assert journal.append(event) == event
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
    def observe(self, scope: ProjectScope) -> tuple[DatabaseObservation, ...]:
        return (DatabaseObservation(ref=_database_ref(), scope=scope, evidence_digest="digest-1"),)

    def quarantine(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        return DatabaseCreation(
            ref=_database_ref(),
            receipt=CreationReceipt(operation=operation, owned_resource_ids=("database-1",)),
        )

    def delete(self, creation: DatabaseCreation) -> None:
        return None

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        return CleanupReport()


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
