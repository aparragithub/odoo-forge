from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from odoo_forge.database.types import CreationReceipt, DatabaseCreation, OperationIdentity
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
    evaluate_expiration,
)
from odoo_forge.tenancy.types import ProjectScope

RecoveryOutcome = LifecycleOutcome


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
        records = tuple(self.registry.list(scope))
        observations = tuple(self.gateway.observe(scope))
        record_keys = tuple((r.resource.resource_kind, r.resource.identifier) for r in records)
        observation_keys = tuple(("database", o.ref.identifier) for o in observations)
        results: list[RecoveryResult] = []
        for key in sorted(set(record_keys) | set(observation_keys)):
            if record_keys.count(key) > 1 or observation_keys.count(key) > 1:
                results.append(self._human(policy, authorization, "duplicate-evidence"))
                continue
            record = next((r for r, item in zip(records, record_keys, strict=True) if item == key), None)  # fmt: skip  # noqa: E501
            observation = next((o for o, item in zip(observations, observation_keys, strict=True) if item == key), None)  # fmt: skip  # noqa: E501
            results.append(self._recover(scope, policy, authorization, record, observation, delete, wait, now))  # fmt: skip  # noqa: E501
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
    ) -> RecoveryResult:
        if not authorization.approved:
            return self._human(policy, authorization, "unauthorized")
        if observation is not None:
            if observation.scope != scope:
                return self._human(policy, authorization, "scope-mismatch")
            if not _eligible(observation, policy, now):
                return self._human(policy, authorization, "ineligible", observation.evidence_digest)
        if record is None:
            if observation is None or not observation.ownership_valid:
                return self._human(policy, authorization, "invalid-ownership")
            current = _matching(self.gateway.observe(observation.scope), observation)
            if current is None or not current.ownership_valid:
                return self._human(policy, authorization, "invalid-ownership")
            if current.evidence_digest != observation.evidence_digest:
                return self._human(policy, authorization, "evidence-drift", current.evidence_digest)
            self.gateway.quarantine(observation.ref); self.gateway.adopt(observation.ref)  # fmt: skip  # noqa: E501,E702
            return self._finish(
                policy,
                authorization,
                "adopted",
                RecoveryOutcome.ADOPTED,
                observation.evidence_digest,
            )
        if observation is None:
            self.gateway.reconcile(_operation(record))
            return self._finish(policy, authorization, "registry-only", RecoveryOutcome.RECONCILED)
        if not observation.ownership_valid:
            return self._human(
                policy, authorization, "invalid-ownership", observation.evidence_digest
            )
        if not _lineage_matches(record, observation):
            return self._human(
                policy, authorization, "lineage-mismatch", observation.evidence_digest
            )
        try:
            current_record = self.registry.get(record.pointer)
        except InstanceRecordNotFoundError:
            return self._human(policy, authorization, "registry-drift", observation.evidence_digest)
        current = _matching(self.gateway.observe(scope), observation)
        if current_record != record or current is None:
            return self._human(policy, authorization, "evidence-drift", observation.evidence_digest)
        if not current.ownership_valid:
            return self._human(policy, authorization, "invalid-ownership", current.evidence_digest)
        if not _lineage_matches(record, current):
            return self._human(policy, authorization, "lineage-mismatch", current.evidence_digest)
        if current.evidence_digest != observation.evidence_digest:
            return self._human(policy, authorization, "evidence-drift", current.evidence_digest)
        quarantined = self.gateway.quarantine(observation.ref)
        if not delete:
            return self._finish(policy, authorization, "quarantined", RecoveryOutcome.QUARANTINED)
        if wait > timedelta():
            return self._finish(policy, authorization, "quarantine-wait", RecoveryOutcome.QUARANTINED, residuals=("wait",))  # fmt: skip  # noqa: E501
        changed = _matching(self.gateway.observe(scope), observation)
        if changed is None or changed.evidence_digest != observation.evidence_digest:
            digest = changed.evidence_digest if changed is not None else "missing"
            return self._finish(policy, authorization, "evidence-changed", RecoveryOutcome.CANCELLED, digest)  # fmt: skip  # noqa: E501
        creation = DatabaseCreation(ref=quarantined, receipt=CreationReceipt(operation=_operation(record), owned_resource_ids=(quarantined.identifier,)))  # fmt: skip  # noqa: E501
        self.gateway.delete(creation)
        residuals = self._cleanup(creation.receipt)
        if residuals:
            return self._finish(policy, authorization, "partial-cleanup", RecoveryOutcome.HUMAN_INTERVENTION, residuals=residuals)  # fmt: skip  # noqa: E501
        return self._finish(policy, authorization, "deleted", RecoveryOutcome.DELETED)

    def _cleanup(self, receipt: CreationReceipt) -> tuple[str, ...]:
        for _ in range(self.max_cleanup_retries + 1):
            residuals = self.gateway.cleanup(receipt).residual_failures
            if not residuals: return ()  # fmt: skip  # noqa: E701
        return residuals

    def _human(
        self, p: LifecyclePolicy, a: LifecycleAuthorization, code: str, digest: str = "registry"
    ) -> RecoveryResult:
        return self._finish(p, a, code, RecoveryOutcome.HUMAN_INTERVENTION, digest)

    def _finish(
        self,
        policy: LifecyclePolicy,
        authorization: LifecycleAuthorization,
        code: str,
        outcome: RecoveryOutcome,
        digest: str = "registry",
        residuals: tuple[str, ...] = (),
    ) -> RecoveryResult:
        values = tuple(LifecycleResidual(code=code, detail=value) for value in residuals)
        if not values and code not in {"adopted", "quarantined", "registry-only", "deleted"}:
            values = (LifecycleResidual(code=code, detail=code),)
        self.journal.append(LifecycleJournalEvent(policy=policy, evidence=LifecycleEvidence(source="lifecycle", digest=digest), authorization=authorization, outcome=outcome, residuals=values))  # fmt: skip  # noqa: E501
        return RecoveryResult(outcome=outcome, residuals=values)


def _matching(
    observations: tuple[DatabaseObservation, ...], expected: DatabaseObservation
) -> DatabaseObservation | None:
    matches = tuple(item for item in observations if item.ref.identifier == expected.ref.identifier)
    return matches[0] if len(matches) == 1 else None


def _eligible(
    observation: DatabaseObservation, policy: LifecyclePolicy, now: datetime | None
) -> bool:
    if observation.last_activity is None:
        return False
    decision = evaluate_expiration(LifecycleResource(resource_id=observation.ref.identifier, resource_class=observation.resource_class, last_activity=observation.last_activity), now or datetime.now(UTC), policy)  # fmt: skip  # noqa: E501
    return decision.eligible and decision.mutation_allowed


def _lineage_matches(record: InstanceRecord, observation: DatabaseObservation) -> bool:
    if record.receipt is None or observation.receipt is None:
        return False
    return record.receipt.operation == observation.receipt.operation and observation.ref.identifier in record.receipt.owned_resource_ids and observation.ref.identifier in observation.receipt.owned_resource_ids  # fmt: skip  # noqa: E501


def _operation(record: InstanceRecord) -> OperationIdentity:
    value = record.receipt.operation.operation_id if record.receipt else record.pointer.instance_id.value  # fmt: skip  # noqa: E501
    return OperationIdentity(value=value)
