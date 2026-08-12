"""Immutable, provider-neutral exposure reconciliation values."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from odoo_forge.backend.status import InstanceRef
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.deployment_spec.types import DeploymentSpec
from odoo_forge.durable_operations.types import (
    DurableOperationIdentity,
    RedactedEvidence,
)
from odoo_forge.resource_ownership.types import OwnershipRecord
from odoo_forge.tenancy.types import ProjectScope


class _ExposureValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ExposureOutcome(StrEnum):
    """Durable outcomes exposed by an exposure reconciler."""

    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class ExposureCheckStatus(StrEnum):
    """Status of one implemented HTTP exposure check."""

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class TlsStatus(StrEnum):
    """TLS status for the first delivery; TLS application is deferred."""

    DEFERRED = "deferred"


class ExposureRequest(_ExposureValue):
    """Provider-neutral input for one operation-scoped exposure reconciliation."""

    instance: InstanceRef
    deployment: DeploymentSpec
    scope: ProjectScope
    operation: DurableOperationIdentity
    ownership: tuple[OwnershipRecord, ...] = ()
    credential_handles: tuple[CredentialHandle, ...] = ()


class ExposureResult(_ExposureValue):
    """Redacted exposure outcome with implemented HTTP readiness separated from TLS."""

    operation: DurableOperationIdentity
    outcome: ExposureOutcome
    routing_status: ExposureCheckStatus = ExposureCheckStatus.PENDING
    dns_status: ExposureCheckStatus = ExposureCheckStatus.PENDING
    ready: bool = False
    tls_status: TlsStatus = TlsStatus.DEFERRED
    tls_ready: bool = False
    ownership: tuple[OwnershipRecord, ...] = ()
    evidence: tuple[RedactedEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_readiness_scope(self) -> "ExposureResult":
        if self.tls_ready:
            raise ValueError("TLS is deferred and cannot make exposure ready")
        if self.ready and (
            self.outcome is not ExposureOutcome.READY
            or self.routing_status is not ExposureCheckStatus.VERIFIED
            or self.dns_status is not ExposureCheckStatus.VERIFIED
        ):
            raise ValueError(
                "implemented exposure readiness requires verified HTTP routing and DNS"
            )
        return self


__all__ = [
    "ExposureCheckStatus",
    "ExposureOutcome",
    "ExposureRequest",
    "ExposureResult",
    "TlsStatus",
]
