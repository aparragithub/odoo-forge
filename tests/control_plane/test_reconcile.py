from __future__ import annotations

import pytest

from odoo_forge.backend.status import InstanceRef, InstanceStatus, RoleStatus
from odoo_forge.control_plane.models import ReconciliationOutcome
from odoo_forge.control_plane.reconcile import Reconciler
from odoo_forge.instance_registry import (
    InstanceId,
    InstancePointer,
    InstanceRecord,
)
from odoo_forge.resource_ownership import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId


def _pointer(instance_id: str = "alpha") -> InstancePointer:
    return InstancePointer(
        scope=ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1"),
        instance_id=InstanceId(value=instance_id),
    )


def _record(instance_id: str = "alpha", identifier: str | None = None) -> InstanceRecord:
    return InstanceRecord(
        pointer=_pointer(instance_id),
        resource=ResourceRef(
            identifier=identifier or f"odoo-forge-project-1-{instance_id}",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def _healthy_status() -> InstanceStatus:
    healthy = RoleStatus(running=True, state="healthy", ready=True)
    return InstanceStatus(odoo=healthy, postgres=healthy)


def _drifted_status() -> InstanceStatus:
    exited = RoleStatus(running=False, state="exited", ready=False)
    healthy = RoleStatus(running=True, state="healthy", ready=True)
    return InstanceStatus(odoo=exited, postgres=healthy)


class _Registry:
    def __init__(self, records: tuple[InstanceRecord, ...] = ()) -> None:
        self.records = records
        self.list_error: Exception | None = None

    def store(self, record: InstanceRecord) -> InstanceRecord:
        raise AssertionError("reconciliation must remain read-only")

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        if self.list_error is not None:
            raise self.list_error
        return self.records

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        for record in self.records:
            if record.pointer == pointer:
                return record
        from odoo_forge.instance_registry import InstanceRecordNotFoundError

        raise InstanceRecordNotFoundError(pointer)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (_healthy_status(), ReconciliationOutcome.FRESH),
        (_drifted_status(), ReconciliationOutcome.DRIFTED),
    ],
)
def test_list_reconciles_truthful_and_drifted_rows(
    status: InstanceStatus, expected: ReconciliationOutcome
) -> None:
    record = _record()
    result = Reconciler(_Registry((record,)), lambda ref: status).list(record.pointer.scope)

    assert result.outcome is expected
    assert len(result.rows) == 1
    assert result.rows[0].record == record
    assert result.rows[0].live == status


def test_running_but_not_ready_live_status_is_drifted() -> None:
    record = _record()
    starting = RoleStatus(running=True, state="starting", ready=False)
    status = InstanceStatus(odoo=starting, postgres=_healthy_status().postgres)

    result = Reconciler(_Registry((record,)), lambda ref: status).list(record.pointer.scope)

    assert result.outcome is ReconciliationOutcome.DRIFTED
    assert result.rows[0].outcome is ReconciliationOutcome.DRIFTED
    assert result.rows[0].live == status


def test_provider_failure_is_stale_and_never_fresh() -> None:
    record = _record()

    def unavailable(ref: InstanceRef) -> InstanceStatus:
        raise RuntimeError("secret docker endpoint")

    result = Reconciler(_Registry((record,)), unavailable).list(record.pointer.scope)

    assert result.outcome is ReconciliationOutcome.STALE_UNVERIFIED
    assert result.rows[0].outcome is ReconciliationOutcome.STALE_UNVERIFIED
    assert result.rows[0].live is None
    assert result.rows[0].detail == "live status could not be verified"


def test_empty_registry_is_explicitly_empty() -> None:
    scope = _pointer().scope

    result = Reconciler(_Registry(), lambda ref: _healthy_status()).list(scope)

    assert result.outcome is ReconciliationOutcome.EMPTY
    assert result.rows == ()


def test_persistence_failure_is_typed_and_redacted() -> None:
    registry = _Registry()
    registry.list_error = RuntimeError("password=top-secret")
    scope = _pointer().scope

    result = Reconciler(registry, lambda ref: _healthy_status()).list(scope)

    assert result.outcome is ReconciliationOutcome.PERSISTENCE_ERROR
    assert result.rows == ()
    assert result.detail == "instance registry could not be read"


def test_multiple_rows_preserve_deterministic_order_and_isolate_failure() -> None:
    alpha = _record("alpha")
    zeta = _record("zeta")

    def status(ref: InstanceRef) -> InstanceStatus:
        if ref.instance == "zeta":
            raise RuntimeError("private provider failure")
        return _healthy_status()

    result = Reconciler(_Registry((zeta, alpha)), status).list(alpha.pointer.scope)

    assert result.outcome is ReconciliationOutcome.PARTIAL_FAILURE
    assert [row.record.pointer.instance_id.value for row in result.rows] == ["alpha", "zeta"]
    assert result.rows[0].outcome is ReconciliationOutcome.FRESH
    assert result.rows[1].outcome is ReconciliationOutcome.PARTIAL_FAILURE
    assert result.rows[0].live == _healthy_status()
    assert result.rows[1].live is None


def test_get_missing_pointer_returns_empty_without_provider_call() -> None:
    pointer = _pointer("missing")
    calls: list[InstanceRef] = []

    def status(ref: InstanceRef) -> InstanceStatus:
        calls.append(ref)
        return _healthy_status()

    result = Reconciler(_Registry(), status).get(pointer)

    assert result.outcome is ReconciliationOutcome.EMPTY
    assert result.rows == ()
    assert calls == []


def test_canonical_resource_handle_maps_to_existing_instance_ref() -> None:
    record = _record()
    observed: list[InstanceRef] = []

    def status(ref: InstanceRef) -> InstanceStatus:
        observed.append(ref)
        return _healthy_status()

    Reconciler(_Registry((record,)), status).list(record.pointer.scope)

    assert observed == [
        InstanceRef(
            project="project-1",
            instance="alpha",
            network="odoo-forge-project-1-alpha",
            postgres_container="odoo-forge-project-1-alpha-db",
            odoo_container="odoo-forge-project-1-alpha-odoo",
        )
    ]


@pytest.mark.parametrize("identifier", ["bad handle", "odoo-forge-project-1-beta"])
def test_malformed_or_contradictory_handle_is_row_local_unverified(
    identifier: str,
) -> None:
    record = _record(identifier=identifier)
    calls: list[InstanceRef] = []

    def status(ref: InstanceRef) -> InstanceStatus:
        calls.append(ref)
        return _healthy_status()

    result = Reconciler(_Registry((record,)), status).list(record.pointer.scope)

    assert result.outcome is ReconciliationOutcome.STALE_UNVERIFIED
    assert result.rows[0].outcome is ReconciliationOutcome.STALE_UNVERIFIED
    assert result.rows[0].live is None
    assert result.rows[0].detail == "resource handle could not be verified"
    assert calls == []


def test_outcome_enum_has_exactly_six_values() -> None:
    assert {outcome.value for outcome in ReconciliationOutcome} == {
        "fresh",
        "drifted",
        "stale_unverified",
        "empty",
        "persistence_error",
        "partial_failure",
    }
