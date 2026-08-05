"""Immutable provider-neutral data-environment contract values."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from odoo_forge.data_artifacts.types import (
    _SECRET_OR_CONNECTION_TEXT,
    _ArtifactValue,
    require_safe_opaque_identifier,
)
from odoo_forge.tenancy.types import ProjectScope


def _identifier(value: str, field_name: str) -> str:
    return require_safe_opaque_identifier(value, field_name)


class EnvironmentLifecycle(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class EnvironmentOutcomeCode(StrEnum):
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    FAILED = "failed"


class EnvironmentFailureCode(StrEnum):
    AUTHORITY_UNAVAILABLE = "authority_unavailable"
    INVALID_DEFINITION = "invalid_definition"
    RAW_GRANT_REQUIRED = "raw_grant_required"
    RECOVERY_POINT_UNAVAILABLE = "recovery_point_unavailable"
    RECOVERY_RESTORE_FAILED = "recovery_restore_failed"
    RECOVERY_VERIFICATION_FAILED = "recovery_verification_failed"


class EnvironmentRelationship(_ArtifactValue):
    source_environment_id: str
    target_environment_id: str

    @field_validator("source_environment_id", "target_environment_id")
    @classmethod
    def require_safe_ids(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name or "environment id")

    @model_validator(mode="after")
    def require_distinct_environments(self) -> EnvironmentRelationship:
        if self.source_environment_id == self.target_environment_id:
            raise ValueError("source and target environments must differ")
        return self


class DataEnvironmentDefinition(_ArtifactValue):
    """Canonical control-plane definition; selectors cannot replace it."""

    environment_id: str
    owner: str
    scope: ProjectScope
    lifecycle: EnvironmentLifecycle
    policy_ref: str
    relationships: tuple[EnvironmentRelationship, ...] = ()

    @field_validator("environment_id", "policy_ref")
    @classmethod
    def require_safe_references(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name or "reference")

    @field_validator("owner")
    @classmethod
    def require_safe_owner(cls, value: str) -> str:
        return _identifier(value, "owner")


class RawDataGrant(_ArtifactValue):
    """A separate, scoped, attributable, expiring raw-data exception."""

    operation_id: str
    environment_id: str
    grantor: str
    expires_at: datetime
    reason: str = Field(min_length=1)
    audit_reference: str

    @field_validator("operation_id", "environment_id", "audit_reference")
    @classmethod
    def require_safe_references(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name or "reference")

    @field_validator("grantor")
    @classmethod
    def require_safe_grantor(cls, value: str) -> str:
        return _identifier(value, "grantor")

    @field_validator("reason")
    @classmethod
    def require_redacted_reason(cls, value: str) -> str:
        if not value.strip() or _SECRET_OR_CONNECTION_TEXT.search(value):
            raise ValueError("grant reason must be present and redacted")
        return value

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("grant expiry must include timezone information")
        return value


class EnvironmentOperationOutcome(_ArtifactValue):
    """Terminal operation result that cannot represent an ambiguous success."""

    code: EnvironmentOutcomeCode
    failure_code: EnvironmentFailureCode | None = None
    redacted_detail: str | None = None

    @model_validator(mode="after")
    def require_fail_closed_state(self) -> EnvironmentOperationOutcome:
        if self.redacted_detail is not None and _SECRET_OR_CONNECTION_TEXT.search(
            self.redacted_detail
        ):
            raise ValueError("outcome detail must be redacted")
        if self.code is EnvironmentOutcomeCode.SUCCEEDED and self.failure_code is not None:
            raise ValueError("successful outcomes cannot carry failure evidence")
        if self.code is not EnvironmentOutcomeCode.SUCCEEDED and self.failure_code is None:
            raise ValueError("non-success outcomes require failure evidence")
        return self

    @property
    def succeeded(self) -> bool:
        return self.code is EnvironmentOutcomeCode.SUCCEEDED


__all__ = [
    "DataEnvironmentDefinition",
    "EnvironmentLifecycle",
    "EnvironmentFailureCode",
    "EnvironmentOperationOutcome",
    "EnvironmentOutcomeCode",
    "EnvironmentRelationship",
    "RawDataGrant",
]
