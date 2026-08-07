from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from odoo_forge.database.types import (
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    OperationIdentity,
)
from odoo_forge.instance_registry.errors import InstanceRecordNotFoundError
from odoo_forge.instance_registry.types import InstanceRecord
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.ports.resource_lifecycle import DatabaseLifecycleGateway, LifecycleJournal
from odoo_forge.resource_lifecycle.types import (
    DatabaseObservation,
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
    evaluate_expiration,
)
from odoo_forge.tenancy.types import ProjectScope

RecoveryOutcome = LifecycleOutcome


class _HistoryContradiction(Exception):
    pass


@dataclass(frozen=True)
class RecoveryResult:
    outcome: RecoveryOutcome
    residuals: tuple[LifecycleResidual, ...] = ()


class LifecycleService:
    def __init__(
        self,
        *,
        registry: InstanceRegistry,
        gateway: DatabaseLifecycleGateway,
        journal: LifecycleJournal,
        max_cleanup_retries: int = 2,
    ) -> None:
        if max_cleanup_retries < 0:
            raise ValueError("max_cleanup_retries must not be negative")
        self.registry, self.gateway, self.journal = registry, gateway, journal
        self.max_cleanup_retries = max_cleanup_retries

    def run(
        self,
        scope: ProjectScope,
        policy: LifecyclePolicy,
        authorization: LifecycleAuthorization,
        *,
        delete: bool = False,
        wait: timedelta = timedelta(),
        now: datetime | None = None,
    ) -> tuple[RecoveryResult, ...]:
        if wait < timedelta():
            raise ValueError("wait must not be negative")
        records = tuple(self.registry.list(scope))
        observations = tuple(self.gateway.observe(scope))
        histories = tuple(
            event.history for event in self.journal.events() if event.history is not None
        )
        record_keys = tuple((r.resource.resource_kind, r.resource.identifier) for r in records)
        observation_keys = tuple(("database", o.ref.identifier) for o in observations)
        history_keys = tuple(("database", h.resource.identifier) for h in histories)
        self._append_action(
            policy,
            authorization,
            LifecycleOutcome.ALERTED,
            "run",
            residuals=(
                (LifecycleResidual(code="empty-run", detail="empty-run"),)
                if not (record_keys or observation_keys or history_keys)
                else ()
            ),
            kind="run",
        )
        results: list[RecoveryResult] = []
        for key in sorted(set(record_keys) | set(observation_keys) | set(history_keys)):
            if record_keys.count(key) > 1 or observation_keys.count(key) > 1:
                results.append(self._human(policy, authorization, "duplicate-evidence")); continue  # fmt: skip  # noqa: E501,E702
            record = next((r for r, item in zip(records, record_keys, strict=True) if item == key), None)  # fmt: skip  # noqa: E501
            observation = next((o for o, item in zip(observations, observation_keys, strict=True) if item == key), None)  # fmt: skip  # noqa: E501
            matching_histories = tuple(
                h for h, item in zip(histories, history_keys, strict=True) if item == key
            )
            if len(matching_histories) > 1:
                results.append(self._human(policy, authorization, "duplicate-history"))
                continue
            history = matching_histories[0] if matching_histories else None
            if history is not None:
                try:
                    record = self._record_from_history(history, record)
                except _HistoryContradiction:
                    results.append(self._human(policy, authorization, "history-mismatch"))
                    continue
            results.append(self._recover(scope, policy, authorization, record, observation, delete, wait, now, history))  # fmt: skip  # noqa: E501
        return tuple(results)

    def _recover(
        self,
        scope: ProjectScope,
        policy: LifecyclePolicy,
        authorization: LifecycleAuthorization,
        record: InstanceRecord | None,
        observation: DatabaseObservation | None,
        delete: bool,
        wait: timedelta,
        now: datetime | None,
        history: QuarantineHistory | None = None,
    ) -> RecoveryResult:
        if not authorization.approved: return self._human(policy, authorization, "unauthorized")  # fmt: skip  # noqa: E501,E701
        if history is not None and record is None:
            if not _confirmed_zombie(scope, policy, history, observation):
                return self._human(policy, authorization, "not-confirmed-zombie")
            if delete and not _quarantine_wait_elapsed(history, wait, now):
                return self._human(policy, authorization, "quarantine-wait")
            if not delete and not _valid_timestamp(getattr(history, "quarantined_at", None)):
                return self._human(policy, authorization, "invalid-quarantine-history")
            quarantined = self.gateway.quarantine(history.resource)
            quarantine_history = history.model_copy(update={"resource": quarantined})
            self._append_action(
                policy, authorization, RecoveryOutcome.QUARANTINED, history=quarantine_history
            )
            if delete:
                if not self._revalidate_zombie(scope, policy, quarantine_history):
                    return self._human(policy, authorization, "not-confirmed-zombie")
                creation = DatabaseCreation(
                    ref=quarantined,
                    receipt=CreationReceipt(
                        operation=OperationIdentity(value=history.operation.operation_id),
                        owned_resource_ids=(quarantined.identifier,),
                    ),
                )
                self.gateway.delete(creation)
                self._append_action(
                    policy,
                    authorization,
                    RecoveryOutcome.DELETED,
                    history=quarantine_history,
                )
                residuals = self._cleanup(creation.receipt)
                if residuals:
                    return self._finish(
                        policy,
                        authorization,
                        "partial-cleanup",
                        RecoveryOutcome.HUMAN_INTERVENTION,
                        residuals=residuals,
                        history=quarantine_history,
                    )
                return self._finish(
                    policy,
                    authorization,
                    "deleted",
                    RecoveryOutcome.DELETED,
                    history=quarantine_history,
                )
            return self._finish(
                policy,
                authorization,
                "confirmed-zombie",
                RecoveryOutcome.QUARANTINED,
                residuals=(),
                history=history.model_copy(update={"resource": quarantined}),
            )
        if observation is not None:
            if observation.scope != scope: return self._human(policy, authorization, "scope-mismatch")  # fmt: skip  # noqa: E501,E701
            if not _eligible(observation, policy, now): return self._human(policy, authorization, "ineligible", observation.evidence_digest)  # fmt: skip  # noqa: E501,E701
        if record is None:
            if observation is None or not observation.ownership_valid: return self._human(policy, authorization, "invalid-ownership")  # fmt: skip  # noqa: E501,E701
            failure = self._revalidate(scope, policy, record, observation, now)
            if failure: return self._human(policy, authorization, *failure)  # fmt: skip  # noqa: E501,E701
            quarantined = self.gateway.quarantine(observation.ref)
            self.gateway.adopt(quarantined)
            self._append_action(policy, authorization, RecoveryOutcome.QUARANTINED)
            self._append_action(policy, authorization, RecoveryOutcome.ADOPTED)
            return self._finish(
                policy,
                authorization,
                "adopted",
                RecoveryOutcome.ADOPTED,
                observation.evidence_digest,
            )
        if observation is None:
            if not self._registry_matches(record):
                return self._human(policy, authorization, "registry-drift")
            self.gateway.reconcile(_operation(record))
            self._append_action(policy, authorization, RecoveryOutcome.RECONCILED)
            return self._finish(policy, authorization, "registry-only", RecoveryOutcome.RECONCILED)
        if not observation.ownership_valid: return self._human(policy, authorization, "invalid-ownership", observation.evidence_digest)  # fmt: skip  # noqa: E501,E701
        if not _lineage_matches(record, observation): return self._human(policy, authorization, "lineage-mismatch", observation.evidence_digest)  # fmt: skip  # noqa: E501,E701
        failure = self._revalidate(scope, policy, record, observation, now)
        if failure: return self._human(policy, authorization, *failure)  # fmt: skip  # noqa: E501,E701
        quarantined = self.gateway.quarantine(observation.ref)
        quarantine_history = _quarantine_history(record, observation, quarantined, now)
        self._append_action(
            policy,
            authorization,
            RecoveryOutcome.QUARANTINED,
            observation.evidence_digest,
            quarantine_history,
        )
        if not delete:
            return self._finish(
                policy,
                authorization,
                "quarantined",
                RecoveryOutcome.QUARANTINED,
                history=quarantine_history,
            )
        if wait > timedelta(): return self._finish(policy, authorization, "quarantine-wait", RecoveryOutcome.QUARANTINED, residuals=("wait",), history=quarantine_history)  # fmt: skip  # noqa: E501,E701
        failure = self._revalidate(scope, policy, record, observation, now)
        if failure:
            code, digest = failure
            if code == "evidence-drift": return self._finish(policy, authorization, "evidence-changed", RecoveryOutcome.CANCELLED, digest)  # fmt: skip  # noqa: E501,E701
            return self._human(policy, authorization, code, digest)
        creation = DatabaseCreation(ref=quarantined, receipt=CreationReceipt(operation=_operation(record), owned_resource_ids=(quarantined.identifier,)))  # fmt: skip  # noqa: E501
        self.gateway.delete(creation)
        self._append_action(
            policy,
            authorization,
            RecoveryOutcome.DELETED,
            observation.evidence_digest,
            quarantine_history,
        )
        residuals = self._cleanup(creation.receipt)
        if residuals:
            return self._finish(policy, authorization, "partial-cleanup", RecoveryOutcome.HUMAN_INTERVENTION, residuals=residuals, history=quarantine_history)  # fmt: skip  # noqa: E501
        return self._finish(
            policy, authorization, "deleted", RecoveryOutcome.DELETED, history=quarantine_history
        )

    def _record_from_history(
        self, history: QuarantineHistory, current: InstanceRecord | None
    ) -> InstanceRecord | None:
        try:
            record = self.registry.get(history.pointer)
        except InstanceRecordNotFoundError:
            if current is not None and not _record_matches_history(current, history):
                raise _HistoryContradiction from None
            return current
        except Exception as exc:
            raise _HistoryContradiction from exc
        if not _record_matches_history(record, history):
            raise _HistoryContradiction
        if current is not None and not _record_matches_history(current, history):
            raise _HistoryContradiction
        if current is not None and record != current:
            return current
        return record

    def _revalidate_zombie(
        self, scope: ProjectScope, policy: LifecyclePolicy, history: QuarantineHistory
    ) -> bool:
        try:
            self.registry.get(history.pointer)
        except InstanceRecordNotFoundError:
            pass
        else:
            return False
        observations = tuple(
            observation
            for observation in self.gateway.observe(scope)
            if observation.ref == history.resource
        )
        return len(observations) == 0 or (
            len(observations) == 1 and _confirmed_zombie(scope, policy, history, observations[0])
        )

    def _append_action(
        self,
        policy: LifecyclePolicy,
        authorization: LifecycleAuthorization,
        outcome: RecoveryOutcome,
        digest: str = "registry",
        history: QuarantineHistory | None = None,
        residuals: tuple[LifecycleResidual, ...] = (),
        kind: str = "action",
    ) -> None:
        self.journal.append(
            LifecycleJournalEvent(
                policy=policy,
                evidence=LifecycleEvidence(source="lifecycle", digest=digest),
                authorization=authorization,
                outcome=outcome,
                residuals=residuals,
                history=history,
                kind=kind,
            )
        )

    def _registry_matches(self, record: InstanceRecord) -> bool:
        try: return self.registry.get(record.pointer) == record  # fmt: skip  # noqa: E701
        except InstanceRecordNotFoundError: return False  # fmt: skip  # noqa: E701

    def _revalidate(
        self,
        scope: ProjectScope,
        policy: LifecyclePolicy,
        record: InstanceRecord | None,
        expected: DatabaseObservation,
        now: datetime | None,
    ) -> tuple[str, str] | None:
        if record is not None and not self._registry_matches(record): return "registry-drift", expected.evidence_digest  # fmt: skip  # noqa: E501,E701
        current = _matching(self.gateway.observe(scope), expected)
        if current is None: return "evidence-drift", "missing"  # fmt: skip  # noqa: E701
        if current.scope != scope: return "scope-mismatch", current.evidence_digest  # fmt: skip  # noqa: E501,E701
        if not _eligible(current, policy, now): return "ineligible", current.evidence_digest  # fmt: skip  # noqa: E501,E701
        if not current.ownership_valid: return "invalid-ownership", current.evidence_digest  # fmt: skip  # noqa: E501,E701
        if record is not None and not _lineage_matches(record, current): return "lineage-mismatch", current.evidence_digest  # fmt: skip  # noqa: E501,E701
        if record is None and current.receipt != expected.receipt: return "lineage-mismatch", current.evidence_digest  # fmt: skip  # noqa: E501,E701
        if current.evidence_digest != expected.evidence_digest: return "evidence-drift", current.evidence_digest  # fmt: skip  # noqa: E501,E701
        return None

    def _cleanup(self, receipt: CreationReceipt) -> tuple[str, ...]:
        for _ in range(self.max_cleanup_retries + 1):
            residuals = self.gateway.cleanup(receipt).residual_failures
            if not residuals: return ()  # fmt: skip  # noqa: E701
        return residuals

    def _human(self, p: LifecyclePolicy, a: LifecycleAuthorization, code: str, digest: str = "registry") -> RecoveryResult:  # fmt: skip  # noqa: E501
        return self._finish(p, a, code, RecoveryOutcome.HUMAN_INTERVENTION, digest)

    def _finish(
        self,
        policy: LifecyclePolicy,
        authorization: LifecycleAuthorization,
        code: str,
        outcome: RecoveryOutcome,
        digest: str = "registry",
        residuals: tuple[str, ...] = (),
        history: QuarantineHistory | None = None,
    ) -> RecoveryResult:
        values = tuple(LifecycleResidual(code=code, detail=value) for value in residuals)
        if not values and code not in {"adopted", "quarantined", "registry-only", "deleted"}: values = (LifecycleResidual(code=code, detail=code),)  # fmt: skip  # noqa: E501,E701
        self.journal.append(LifecycleJournalEvent(policy=policy, evidence=LifecycleEvidence(source="lifecycle", digest=digest), authorization=authorization, outcome=outcome, residuals=values, history=None))  # fmt: skip  # noqa: E501
        return RecoveryResult(outcome=outcome, residuals=values)


def _quarantine_history(
    record: InstanceRecord,
    observation: DatabaseObservation,
    resource: DatabaseRef,
    now: datetime | None,
) -> QuarantineHistory:
    assert record.receipt is not None
    return QuarantineHistory(
        pointer=record.pointer,
        scope=observation.scope,
        resource=resource,
        operation=record.receipt.operation,
        evidence_digest=observation.evidence_digest,
        resource_class=observation.resource_class,
        quarantined_at=now or datetime.now(UTC),
    )


def _confirmed_zombie(
    scope: ProjectScope,
    policy: LifecyclePolicy,
    history: QuarantineHistory,
    observation: DatabaseObservation | None,
) -> bool:
    if (
        history.scope != scope
        or history.pointer.scope != scope
        or history.resource_class not in {ResourceClass.DEV, ResourceClass.QA}
        or not policy.is_approved(history.resource_class)
    ):
        return False
    if observation is None:
        return True
    return (
        observation.scope == scope
        and observation.ref == history.resource
        and observation.resource_class == history.resource_class
        and observation.evidence_digest == history.evidence_digest
        and observation.ownership_valid
        and observation.presence in {ProviderPresence.ABSENT, ProviderPresence.INVALID}
        and (observation.receipt is None or observation.receipt.operation == history.operation)
    )


def _record_matches_history(record: InstanceRecord, history: QuarantineHistory) -> bool:
    return (
        record.pointer == history.pointer
        and record.resource.resource_kind == "database"
        and record.resource.identifier == history.resource.identifier
        and record.resource.ownership == history.resource.ownership
        and record.receipt is not None
        and record.receipt.operation == history.operation
    )


def _valid_timestamp(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def _quarantine_wait_elapsed(
    history: QuarantineHistory, wait: timedelta, now: datetime | None
) -> bool:
    current = now or datetime.now(UTC)
    if not _valid_timestamp(getattr(history, "quarantined_at", None)) or not _valid_timestamp(
        current
    ):
        return False
    quarantined_at = history.quarantined_at
    return quarantined_at <= current and current - quarantined_at >= wait


def _matching(
    observations: tuple[DatabaseObservation, ...], expected: DatabaseObservation
) -> DatabaseObservation | None:
    return (matches[0] if len(matches) == 1 else None) if (matches := tuple(item for item in observations if item.ref.identifier == expected.ref.identifier)) else None  # fmt: skip  # noqa: E501


def _eligible(
    observation: DatabaseObservation, policy: LifecyclePolicy, now: datetime | None
) -> bool:
    if observation.last_activity is None: return False  # fmt: skip  # noqa: E701
    decision = evaluate_expiration(LifecycleResource(resource_id=observation.ref.identifier, resource_class=observation.resource_class, last_activity=observation.last_activity), now or datetime.now(UTC), policy)  # fmt: skip  # noqa: E501
    return decision.eligible and decision.mutation_allowed


def _lineage_matches(record: InstanceRecord, observation: DatabaseObservation) -> bool:
    return (record_receipt := record.receipt) is not None and (observation_receipt := observation.receipt) is not None and record_receipt.operation == observation_receipt.operation and observation.ref.identifier in record_receipt.owned_resource_ids and observation.ref.identifier in observation_receipt.owned_resource_ids  # fmt: skip  # noqa: E501


def _operation(record: InstanceRecord) -> OperationIdentity:
    return OperationIdentity(value=record.receipt.operation.operation_id if record.receipt else record.pointer.instance_id.value)  # fmt: skip  # noqa: E501
