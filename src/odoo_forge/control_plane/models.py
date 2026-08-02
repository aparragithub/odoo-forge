"""Typed values for read-only control-plane reconciliation."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from odoo_forge.backend.status import InstanceStatus
from odoo_forge.instance_registry import InstanceRecord


class ReconciliationOutcome(StrEnum):
    """The complete set of read observation outcomes."""

    FRESH = "fresh"
    DRIFTED = "drifted"
    STALE_UNVERIFIED = "stale_unverified"
    EMPTY = "empty"
    PERSISTENCE_ERROR = "persistence_error"
    PARTIAL_FAILURE = "partial_failure"


class _ReconciliationValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ReconciliationRow(_ReconciliationValue):
    """One stored record and its request-scoped live observation."""

    record: InstanceRecord
    live: InstanceStatus | None
    outcome: ReconciliationOutcome
    detail: str | None = None


class ReconciliationResult(_ReconciliationValue):
    """The deterministic envelope returned by a read reconciliation."""

    outcome: ReconciliationOutcome
    rows: tuple[ReconciliationRow, ...]
    detail: str | None = None


__all__ = ["ReconciliationOutcome", "ReconciliationResult", "ReconciliationRow"]
