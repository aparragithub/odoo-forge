"""Provider-neutral recovery recording contract for durable operations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from odoo_forge.durable_operations.types import OperationRevision, RedactedEvidence
from odoo_forge.ports.durable_operation_store import DurableOperationRecord


@runtime_checkable
class DurableOperationRecovery(Protocol):
    """Record workflow-level recovery outcomes without choosing recovery scheduling."""

    def record_attempt(
        self, operation_id: str, expected_revision: OperationRevision, outcome: RedactedEvidence
    ) -> DurableOperationRecord:
        """Atomically record a redacted recovery result against the expected revision."""
        ...


__all__ = ["DurableOperationRecovery"]
