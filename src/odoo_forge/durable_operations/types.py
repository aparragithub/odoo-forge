"""Immutable, provider-neutral durable-operation values."""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_SENSITIVE_TEXT = re.compile(
    r"(?:\b(?:api[_-]?key|artifact[_-]?bytes|authorization|bearer|credential|password|passwd|secret|token)\b\s*[=:]?|://|@)",
    re.IGNORECASE,
)


def _is_safe_identifier(value: str) -> bool:
    return _SAFE_IDENTIFIER.fullmatch(value) is not None and _SENSITIVE_TEXT.search(value) is None


class _DurableValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class LifecycleState(StrEnum):
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    TERMINAL_PENDING = "terminal_pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CLEANUP_REQUIRED = "cleanup_required"
    CLOSED = "closed"


class DurableOperationIdentity(_DurableValue):
    """Stable operation identity bound to one request meaning."""

    operation_id: str = Field(min_length=1)
    request_digest: str = Field(min_length=1)

    def matches_request_digest(self, request_digest: str) -> bool:
        """Return whether a submission has the request meaning already bound here."""
        return self.request_digest == request_digest


class OperationRevision(_DurableValue):
    """Monotonically increasing revision for a durable operation."""

    value: int = Field(ge=0)


class RedactedEvidence(_DurableValue):
    """Minimal audit facts that never retain secrets or protected payload bytes."""

    event: str
    summary: str
    references: tuple[str, ...] = ()

    @field_validator("event", "summary")
    @classmethod
    def validate_redacted_text(cls, value: str) -> str:
        if not value or _SENSITIVE_TEXT.search(value):
            raise ValueError("durable evidence must not contain sensitive or connection material")
        return value

    @field_validator("references")
    @classmethod
    def validate_safe_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _is_safe_identifier(value):
                raise ValueError("durable evidence references must be safe opaque identifiers")
        return values


class CompensationScope(_DurableValue):
    """Invocation-owned resources that are eligible for compensation."""

    operation_id: str
    owned_resource_ids: tuple[str, ...]

    @field_validator("owned_resource_ids")
    @classmethod
    def validate_owned_resource_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not _is_safe_identifier(value):
                raise ValueError("owned resource IDs must be safe opaque identifiers")
        return values

    def owns(self, resource_id: str) -> bool:
        """Return whether the resource was recorded as invocation-owned."""
        return resource_id in self.owned_resource_ids


__all__ = [
    "CompensationScope",
    "DurableOperationIdentity",
    "LifecycleState",
    "OperationRevision",
    "RedactedEvidence",
]
