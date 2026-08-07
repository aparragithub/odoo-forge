from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from odoo_forge.database.types import DatabaseRef
from odoo_forge.tenancy.types import ProjectScope


class _LifecycleValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ResourceClass(StrEnum):
    DEV = "dev"
    QA = "qa"
    PROD = "prod"


class ExpirationAction(StrEnum):
    EXPIRE = "expire"
    ALERT_AUDIT_ONLY = "alert_audit_only"


class LifecycleOutcome(StrEnum):
    EXPIRED = "expired"
    ALERTED = "alerted"


class ResourceOverride(_LifecycleValue):
    resource_id: str
    ttl: timedelta


class LifecyclePolicy(_LifecycleValue):
    ttl: timedelta
    grace: timedelta
    approved_classes: frozenset[ResourceClass] = frozenset({ResourceClass.DEV, ResourceClass.QA})
    overrides: tuple[ResourceOverride, ...] = ()

    def is_approved(self, resource_class: ResourceClass) -> bool:
        return resource_class in self.approved_classes

    def ttl_for(self, resource_id: str) -> timedelta:
        for override in self.overrides:
            if override.resource_id == resource_id:
                return override.ttl
        return self.ttl


class LifecycleResource(_LifecycleValue):
    resource_id: str
    resource_class: ResourceClass
    last_activity: datetime


class ExpirationDecision(_LifecycleValue):
    action: ExpirationAction
    eligible: bool
    mutation_allowed: bool


def evaluate_expiration(
    resource: LifecycleResource, now: datetime, policy: LifecyclePolicy
) -> ExpirationDecision:
    if resource.resource_class is ResourceClass.PROD or not policy.is_approved(
        resource.resource_class
    ):
        return ExpirationDecision(
            action=ExpirationAction.ALERT_AUDIT_ONLY,
            eligible=False,
            mutation_allowed=False,
        )
    eligible = now - resource.last_activity >= policy.ttl_for(resource.resource_id) + policy.grace
    return ExpirationDecision(
        action=ExpirationAction.EXPIRE if eligible else ExpirationAction.ALERT_AUDIT_ONLY,
        eligible=eligible,
        mutation_allowed=eligible,
    )


def reset_activity_baseline(
    resource: LifecycleResource, occurred_at: datetime
) -> LifecycleResource:
    return resource.model_copy(update={"last_activity": occurred_at})


class LifecycleEvidence(_LifecycleValue):
    source: str
    digest: str


class LifecycleAuthorization(_LifecycleValue):
    actor: str
    reason: str
    approved: bool = True


class LifecycleResidual(_LifecycleValue):
    code: str
    detail: str


class LifecycleJournalEvent(_LifecycleValue):
    policy: LifecyclePolicy
    evidence: LifecycleEvidence
    authorization: LifecycleAuthorization
    outcome: LifecycleOutcome
    residuals: tuple[LifecycleResidual, ...] = ()


class DatabaseObservation(_LifecycleValue):
    ref: DatabaseRef
    scope: ProjectScope
    evidence_digest: str
    ownership_valid: bool = True


__all__ = [
    "DatabaseObservation",
    "ExpirationAction",
    "ExpirationDecision",
    "LifecycleAuthorization",
    "LifecycleEvidence",
    "LifecycleJournalEvent",
    "LifecycleOutcome",
    "LifecyclePolicy",
    "LifecycleResource",
    "LifecycleResidual",
    "ResourceClass",
    "ResourceOverride",
    "evaluate_expiration",
    "reset_activity_baseline",
]
