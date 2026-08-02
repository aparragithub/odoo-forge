"""Deterministic, read-only reconciliation against live backend observations."""

from collections.abc import Callable, Sequence

from odoo_forge.backend.status import InstanceRef, InstanceStatus, sanitize_name
from odoo_forge.control_plane.models import (
    ReconciliationOutcome,
    ReconciliationResult,
    ReconciliationRow,
)
from odoo_forge.instance_registry import (
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
)
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.tenancy import ProjectScope

StatusReader = Callable[[InstanceRef], InstanceStatus]

_LIVE_STATUS_ERROR = "live status could not be verified"
_HANDLE_ERROR = "resource handle could not be verified"
_PERSISTENCE_ERROR = "instance registry could not be read"


class Reconciler:
    """Read registry records and independently observe each backend instance."""

    def __init__(self, registry: InstanceRegistry, status: StatusReader) -> None:
        self._registry = registry
        self._status = status

    def list(self, scope: ProjectScope) -> ReconciliationResult:
        """Reconcile all records in ``scope`` without mutating either dependency."""
        try:
            records = self._registry.list(scope)
        except Exception:
            return ReconciliationResult(
                outcome=ReconciliationOutcome.PERSISTENCE_ERROR,
                rows=(),
                detail=_PERSISTENCE_ERROR,
            )
        return self._reconcile(records)

    def get(self, pointer: InstancePointer) -> ReconciliationResult:
        """Reconcile one record, returning ``empty`` when it is not registered."""
        try:
            record = self._registry.get(pointer)
        except InstanceRecordNotFoundError:
            return ReconciliationResult(outcome=ReconciliationOutcome.EMPTY, rows=())
        except Exception:
            return ReconciliationResult(
                outcome=ReconciliationOutcome.PERSISTENCE_ERROR,
                rows=(),
                detail=_PERSISTENCE_ERROR,
            )
        return self._reconcile((record,))

    def _reconcile(self, records: Sequence[InstanceRecord]) -> ReconciliationResult:
        ordered = tuple(sorted(records, key=lambda record: record.pointer.instance_id.value))
        if not ordered:
            return ReconciliationResult(outcome=ReconciliationOutcome.EMPTY, rows=())

        rows = tuple(self._reconcile_row(record) for record in ordered)
        outcomes = {row.outcome for row in rows}
        failures = ReconciliationOutcome.STALE_UNVERIFIED in outcomes
        usable = outcomes - {ReconciliationOutcome.STALE_UNVERIFIED}
        if failures and usable:
            outcome = ReconciliationOutcome.PARTIAL_FAILURE
            rows = tuple(
                row.model_copy(update={"outcome": ReconciliationOutcome.PARTIAL_FAILURE})
                if row.outcome is ReconciliationOutcome.STALE_UNVERIFIED
                else row
                for row in rows
            )
        elif ReconciliationOutcome.DRIFTED in outcomes:
            outcome = ReconciliationOutcome.DRIFTED
        elif failures:
            outcome = ReconciliationOutcome.STALE_UNVERIFIED
        else:
            outcome = ReconciliationOutcome.FRESH
        return ReconciliationResult(outcome=outcome, rows=rows)

    def _reconcile_row(self, record: InstanceRecord) -> ReconciliationRow:
        try:
            ref = _instance_ref(record)
        except ValueError:
            return ReconciliationRow(
                record=record,
                live=None,
                outcome=ReconciliationOutcome.STALE_UNVERIFIED,
                detail=_HANDLE_ERROR,
            )

        try:
            live = self._status(ref)
        except Exception:
            return ReconciliationRow(
                record=record,
                live=None,
                outcome=ReconciliationOutcome.STALE_UNVERIFIED,
                detail=_LIVE_STATUS_ERROR,
            )

        return ReconciliationRow(
            record=record,
            live=live,
            outcome=_status_outcome(live),
        )


def _instance_ref(record: InstanceRecord) -> InstanceRef:
    """Build the existing backend handle from one canonical registry handle."""
    project = sanitize_name(record.pointer.scope.project_id)
    instance = sanitize_name(record.pointer.instance_id.value)
    expected_network = f"odoo-forge-{project}-{instance}"
    if (
        record.resource.resource_kind != "instance"
        or record.resource.identifier != expected_network
    ):
        raise ValueError(_HANDLE_ERROR)
    return InstanceRef(
        project=record.pointer.scope.project_id,
        instance=record.pointer.instance_id.value,
        network=record.resource.identifier,
        postgres_container=f"{record.resource.identifier}-db",
        odoo_container=f"{record.resource.identifier}-odoo",
    )


def _status_outcome(status: InstanceStatus) -> ReconciliationOutcome:
    if not status.odoo.running or not status.postgres.running:
        return ReconciliationOutcome.DRIFTED
    if not status.odoo.ready or not status.postgres.ready:
        return ReconciliationOutcome.DRIFTED
    return ReconciliationOutcome.FRESH


__all__ = ["Reconciler", "StatusReader"]
