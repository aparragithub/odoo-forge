"""Behavioral and boundary contracts for the in-memory instance registry fake."""

from __future__ import annotations

import pytest

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry import (
    InstanceId,
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
    InstanceRegistrationConflictError,
    MissingReceiptError,
    ReceiptOverwriteRejectedError,
)
from odoo_forge.resource_ownership import OwnershipReceipt, ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_instances_postgres.fakes import FakeInstanceRegistry


def _scope(tenant: str = "tenant-1", project: str = "project-1") -> ProjectScope:
    return ProjectScope(tenant=TenantId(value=tenant), project_id=project)


def _receipt(operation_id: str = "postgres-docker:op-1") -> OwnershipReceipt:
    return OwnershipReceipt(
        operation=DurableOperationIdentity(operation_id=operation_id, request_digest="a" * 64),
        owned_resource_ids=("container-1",),
    )


def _record(
    instance: str,
    *,
    tenant: str = "tenant-1",
    project: str = "project-1",
    identifier: str | None = None,
) -> InstanceRecord:
    return InstanceRecord(
        pointer=InstancePointer(
            scope=_scope(tenant, project), instance_id=InstanceId(value=instance)
        ),
        resource=ResourceRef(
            identifier=identifier or f"resource-{instance}",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def test_store_and_get_return_the_expected_immutable_record() -> None:
    fake = FakeInstanceRegistry()
    record = _record("instance-1")

    assert fake.store(record) == record
    assert fake.get(record.pointer) == record
    assert fake.list(record.pointer.scope) == (record,)
    assert record == _record("instance-1")


def test_repeated_operations_are_stable_and_side_effect_free() -> None:
    fake = FakeInstanceRegistry()
    record = _record("instance-1")
    fake.store(record)

    assert fake.get(record.pointer) == fake.get(record.pointer)
    assert fake.list(record.pointer.scope) == fake.list(record.pointer.scope)
    assert fake.store(record) == record


def test_get_raises_typed_not_found_with_the_requested_pointer() -> None:
    fake = FakeInstanceRegistry()
    pointer = _record("missing").pointer

    with pytest.raises(InstanceRecordNotFoundError) as excinfo:
        fake.get(pointer)

    assert excinfo.value.pointer == pointer


def test_store_replaces_an_existing_pointer_and_returns_authoritative_record() -> None:
    fake = FakeInstanceRegistry()
    original = _record("instance-1", identifier="original")
    replacement = _record("instance-1", identifier="replacement")

    assert fake.store(original) == original
    assert fake.store(replacement) == replacement
    assert fake.get(replacement.pointer) == replacement
    assert fake.list(replacement.pointer.scope) == (replacement,)


def test_list_filters_exact_scope_orders_by_instance_id_and_returns_tuple() -> None:
    fake = FakeInstanceRegistry()
    first = _record("instance-1")
    second = _record("instance-2")
    other_project = _record("instance-0", project="project-2")
    other_tenant = _record("instance-3", tenant="tenant-2")

    for record in (second, other_project, first, other_tenant):
        fake.store(record)

    result = fake.list(_scope())

    assert result == (first, second)
    assert isinstance(result, tuple)


def test_fake_instances_have_independent_state() -> None:
    populated = FakeInstanceRegistry()
    isolated = FakeInstanceRegistry()
    record = _record("instance-1")

    populated.store(record)

    assert populated.list(record.pointer.scope) == (record,)
    assert isolated.list(record.pointer.scope) == ()
    with pytest.raises(InstanceRecordNotFoundError):
        isolated.get(record.pointer)


def test_fake_module_exports_only_the_fake() -> None:
    import odoo_forge_instances_postgres.fakes as fakes

    assert fakes.__all__ == ["FakeInstanceRegistry"]


def test_register_requires_a_receipt_and_mutates_nothing() -> None:
    fake = FakeInstanceRegistry()
    record = _record("instance-1")

    with pytest.raises(MissingReceiptError):
        fake.register(record)

    assert fake.list(record.pointer.scope) == ()


def test_register_persists_a_new_receipt_bearing_row() -> None:
    fake = FakeInstanceRegistry()
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})

    assert fake.register(record) == record
    assert fake.get(record.pointer) == record


def test_register_is_idempotent_for_an_exact_committed_retry() -> None:
    fake = FakeInstanceRegistry()
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    fake.register(record)

    assert fake.register(record) == record
    assert fake.list(record.pointer.scope) == (record,)


def test_register_rejects_a_conflicting_reuse_of_the_operation_identity() -> None:
    fake = FakeInstanceRegistry()
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    conflicting = _record("instance-2").model_copy(update={"receipt": _receipt()})
    fake.register(record)

    with pytest.raises(InstanceRegistrationConflictError):
        fake.register(conflicting)

    assert fake.get(record.pointer) == record
    with pytest.raises(InstanceRecordNotFoundError):
        fake.get(conflicting.pointer)


def test_store_rejects_overwriting_a_receipt_bearing_row() -> None:
    """`store()` must never invalidate a canonical registration's lineage.

    Rewriting a receipt-bearing row's resource fields while leaving its
    receipt columns untouched would produce a row whose lineage evidence
    contradicts its own content. `store()` is fenced off from those rows
    entirely rather than silently clearing the receipt, since the spec
    requires accepted-registration evidence to be retained, not erased.
    """
    fake = FakeInstanceRegistry()
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    fake.register(record)
    replacement = _record("instance-1", identifier="replacement")

    with pytest.raises(ReceiptOverwriteRejectedError):
        fake.store(replacement)

    assert fake.get(record.pointer) == record


def test_register_rejects_reuse_of_the_same_pointer_under_a_new_operation_id() -> None:
    fake = FakeInstanceRegistry()
    original = _record("instance-1").model_copy(
        update={"receipt": _receipt("postgres-docker:op-1")}
    )
    reuse = _record("instance-1").model_copy(update={"receipt": _receipt("postgres-docker:op-2")})
    fake.register(original)

    with pytest.raises(InstanceRegistrationConflictError):
        fake.register(reuse)

    assert fake.get(original.pointer) == original
