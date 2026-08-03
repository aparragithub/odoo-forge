"""Hermetic behavioral contracts for the PostgreSQL instance registry adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

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
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.resource_ownership import OwnershipReceipt, ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_instances_postgres.adapter import PostgresInstanceRegistry

Row = tuple[object, ...]


def _scope(tenant: str = "tenant-1", project: str = "project-1") -> ProjectScope:
    return ProjectScope(tenant=TenantId(value=tenant), project_id=project)


def _record(
    instance: str,
    *,
    tenant: str = "tenant-1",
    project: str = "project-1",
    identifier: str | None = None,
    kind: str = "instance",
    ownership: ResourceOwnership = ResourceOwnership.CREATED,
) -> InstanceRecord:
    return InstanceRecord(
        pointer=InstancePointer(
            scope=_scope(tenant, project), instance_id=InstanceId(value=instance)
        ),
        resource=ResourceRef(
            identifier=identifier or f"resource-{instance}", resource_kind=kind, ownership=ownership
        ),
    )


def _row(record: InstanceRecord) -> Row:
    return (
        record.pointer.scope.tenant.value,
        record.pointer.scope.project_id,
        record.pointer.instance_id.value,
        record.resource.identifier,
        record.resource.resource_kind,
        record.resource.ownership.value,
    )


def _receipt(operation_id: str = "postgres-docker:op-1") -> OwnershipReceipt:
    return OwnershipReceipt(
        operation=DurableOperationIdentity(operation_id=operation_id, request_digest="a" * 64),
        owned_resource_ids=("container-1",),
    )


def _receipt_row(record: InstanceRecord) -> Row:
    assert record.receipt is not None
    return (*_row(record), *_receipt_fields(record.receipt))


def _receipt_fields(receipt: OwnershipReceipt) -> Row:
    return (
        receipt.operation.operation_id,
        receipt.operation.request_digest,
        list(receipt.owned_resource_ids),
        receipt.live_proof_expected,
    )


class ScriptedCursor:
    def __init__(
        self,
        rows: list[Row | None] | None = None,
        list_rows: list[Row] | None = None,
        list_rows_sequence: list[list[Row]] | None = None,
        error: Exception | None = None,
        error_at: str | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rows, self.list_rows = rows or [], list_rows or []
        self._list_rows_sequence = (
            list(list_rows_sequence) if list_rows_sequence is not None else None
        )
        self.error, self.error_at = error, error_at

    def _raise(self, location: str) -> None:
        if self.error_at == location and self.error is not None:
            raise self.error

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        self._raise("execute")
        self.executed.append((query, parameters))

    def fetchone(self) -> Row | None:
        self._raise("fetch")
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[Row]:
        self._raise("fetch")
        if self._list_rows_sequence is not None:
            return self._list_rows_sequence.pop(0) if self._list_rows_sequence else []
        return self.list_rows


class ScriptedConnection:
    def __init__(
        self,
        cursor: ScriptedCursor,
        commit_error: Exception | None = None,
        rollback_error: Exception | None = None,
    ) -> None:
        self.cursor_instance = cursor
        self.commit_error, self.rollback_error = commit_error, rollback_error
        self.commit_count = self.rollback_count = 0

    def cursor(self) -> ScriptedCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.rollback_count += 1
        if self.rollback_error is not None:
            raise self.rollback_error


@contextmanager
def _lease(connection: ScriptedConnection, releases: list[bool]) -> Iterator[ScriptedConnection]:
    try:
        yield connection
    finally:
        releases.append(True)


class ScriptedAcquirer:
    def __init__(self, *connections: ScriptedConnection) -> None:
        self.connections, self.calls = list(connections), 0
        self.releases: list[bool] = []

    def __call__(self) -> AbstractContextManager[ScriptedConnection]:
        self.calls += 1
        return _lease(self.connections[self.calls - 1], self.releases)


def test_store_is_parameterized_and_returns_authoritative_six_column_row() -> None:
    requested = _record("instance-1", identifier="requested")
    authoritative = _record(
        "instance-1", identifier="database-value", ownership=ResourceOwnership.ADOPTED
    )
    cursor = ScriptedCursor(rows=[None, _row(authoritative)])
    connection = ScriptedConnection(cursor)
    acquirer = ScriptedAcquirer(connection)
    registry = PostgresInstanceRegistry(acquirer)

    assert isinstance(registry, InstanceRegistry)
    assert registry.store(requested) == authoritative
    query, parameters = cursor.executed[1]
    assert parameters == _row(requested) and query.count("%s") == 6
    assert "INSERT INTO public.instance_registry" in query
    assert "ON CONFLICT (tenant_id, project_id, instance_id) DO UPDATE" in query
    assert "RETURNING tenant_id, project_id, instance_id" in query and "updated_at = now()" in query
    assert (connection.commit_count, connection.rollback_count, acquirer.calls) == (1, 0, 1)
    assert acquirer.releases[0]


def test_store_rejects_overwriting_an_existing_receipt_bearing_row() -> None:
    """`store()` must never rewrite a row whose committed lineage it cannot preserve.

    Paired with the fake's equivalent guard: both layers must agree that a
    plain overwrite of a receipt-bearing row is rejected, never silently
    applied and never silently stripped of its receipt.
    """
    requested = _record("instance-1", identifier="replacement")
    cursor = ScriptedCursor(rows=[("postgres-docker:op-1",)])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    with pytest.raises(ReceiptOverwriteRejectedError):
        registry.store(requested)

    assert len(cursor.executed) == 1
    assert connection.commit_count == 0 and connection.rollback_count == 1


def test_store_replaces_by_identity_and_get_reconstructs_all_columns() -> None:
    original = _record("instance-1", identifier="original")
    replacement = _record(
        "instance-1",
        identifier="replacement",
        kind="container",
        ownership=ResourceOwnership.EXTERNAL,
    )
    store_cursor = ScriptedCursor(rows=[None, _row(replacement)])
    get_cursor = ScriptedCursor(rows=[_row(replacement)])
    list_cursor = ScriptedCursor(list_rows=[_row(replacement)])
    acquirer = ScriptedAcquirer(
        ScriptedConnection(store_cursor),
        ScriptedConnection(get_cursor),
        ScriptedConnection(list_cursor),
    )
    registry = PostgresInstanceRegistry(acquirer)

    assert registry.store(original) == replacement
    assert registry.get(replacement.pointer) == replacement
    assert registry.list(replacement.pointer.scope) == (replacement,)
    store_query, store_parameters = store_cursor.executed[1]
    get_query, get_parameters = get_cursor.executed[0]
    assert store_parameters[:3] == get_parameters == ("tenant-1", "project-1", "instance-1")
    assert "ON CONFLICT (tenant_id, project_id, instance_id)" in store_query
    assert "SELECT tenant_id, project_id, instance_id" in get_query
    assert "WHERE tenant_id = %s AND project_id = %s AND instance_id = %s" in get_query
    assert all(
        "CREATE" not in query.upper() and "MIGRATION" not in query.upper()
        for query, _ in store_cursor.executed
    )
    assert acquirer.calls == 3 and all(acquirer.releases)


def test_list_scopes_and_orders_records_and_empty_scope_commits() -> None:
    alpha, zeta = _record("alpha"), _record("zeta")
    cursor, connection = ScriptedCursor(list_rows=[_row(alpha), _row(zeta)]), None
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    assert registry.list(_scope()) == (alpha, zeta)
    query, parameters = cursor.executed[0]
    assert parameters == ("tenant-1", "project-1")
    assert (
        "WHERE tenant_id = %s AND project_id = %s" in query and "ORDER BY instance_id ASC" in query
    )

    empty_connection = ScriptedConnection(ScriptedCursor(list_rows=[]))
    assert (
        PostgresInstanceRegistry(ScriptedAcquirer(empty_connection)).list(
            _scope("tenant-without-records", "project-without-records")
        )
        == ()
    )
    assert (empty_connection.commit_count, empty_connection.rollback_count) == (1, 0)


def test_get_translates_a_missing_row_to_typed_not_found() -> None:
    pointer = _record("missing").pointer
    connection = ScriptedConnection(ScriptedCursor(rows=[None]))
    with pytest.raises(InstanceRecordNotFoundError) as excinfo:
        PostgresInstanceRegistry(ScriptedAcquirer(connection)).get(pointer)
    assert excinfo.value.pointer == pointer
    assert (connection.commit_count, connection.rollback_count) == (0, 1)


@pytest.mark.parametrize("failure_location", ["execute", "fetch", "map", "commit"])
def test_failures_rollback_once_preserve_identity_and_do_not_retry(failure_location: str) -> None:
    failure: Exception = (
        ValueError(failure_location)
        if failure_location == "map"
        else RuntimeError(failure_location)
    )
    requested = _record("instance-1")
    if failure_location == "map":
        cursor = ScriptedCursor(
            rows=[None, ("tenant-1", "project-1", "instance-1", "resource", "instance", "invalid")]
        )
    elif failure_location == "commit":
        cursor = ScriptedCursor(rows=[None, _row(requested)])
    else:
        cursor = ScriptedCursor(error=failure, error_at=failure_location)
    connection = ScriptedConnection(
        cursor,
        commit_error=failure if failure_location == "commit" else None,
    )
    acquirer = ScriptedAcquirer(connection)

    with pytest.raises(type(failure)) as excinfo:
        PostgresInstanceRegistry(acquirer).store(requested)
    assert (
        isinstance(excinfo.value, ValueError)
        if failure_location == "map"
        else excinfo.value is failure
    )
    assert connection.rollback_count == 1 and acquirer.calls == 1 and acquirer.releases[0]
    assert connection.commit_count == (1 if failure_location == "commit" else 0)
    assert (
        len(cursor.executed) == {"execute": 0, "fetch": 1, "map": 2, "commit": 2}[failure_location]
    )


def test_rollback_failure_is_logged_without_replacing_operation_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    operation_failure = RuntimeError("execute")
    rollback_failure = RuntimeError("rollback")
    connection = ScriptedConnection(
        ScriptedCursor(error=operation_failure, error_at="execute"),
        rollback_error=rollback_failure,
    )

    with pytest.raises(RuntimeError) as excinfo:
        PostgresInstanceRegistry(ScriptedAcquirer(connection)).store(_record("instance-1"))

    assert excinfo.value is operation_failure
    assert connection.rollback_count == 1
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.name == "odoo_forge_instances_postgres.adapter"
    assert record.getMessage() == "Transaction rollback failed"
    assert record.exc_info is not None and record.exc_info[1] is rollback_failure


def test_register_requires_a_receipt_and_touches_no_connection() -> None:
    acquirer = ScriptedAcquirer()
    registry = PostgresInstanceRegistry(acquirer)

    with pytest.raises(MissingReceiptError):
        registry.register(_record("instance-1"))

    assert acquirer.calls == 0


def test_register_inserts_a_new_receipt_bearing_row_by_plain_insert() -> None:
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    cursor = ScriptedCursor(list_rows=[], rows=[_receipt_row(record)])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    assert registry.register(record) == record
    lookup_query, lookup_parameters = cursor.executed[0]
    insert_query, insert_parameters = cursor.executed[1]
    assert "WHERE operation_id = %s OR (tenant_id, project_id, instance_id) = (%s, %s, %s)" in (
        lookup_query
    )
    assert lookup_parameters == (
        record.receipt.operation.operation_id,  # type: ignore[union-attr]
        "tenant-1",
        "project-1",
        "instance-1",
    )
    assert "INSERT INTO public.instance_registry" in insert_query
    assert "ON CONFLICT DO NOTHING" in insert_query
    assert insert_parameters == _receipt_row(record)
    assert connection.commit_count == 1


def test_register_converges_a_concurrent_identical_registration_without_a_typed_error() -> None:
    """A losing concurrent IDENTICAL registration must not leak a raw driver error.

    `ON CONFLICT DO NOTHING` lets our own INSERT silently insert zero rows
    when a concurrent identical registration committed between our initial
    lookup and this INSERT; `fetchone()` then returns `None` instead of
    raising `UniqueViolation`. The adapter must re-read the now-committed row
    and converge on the idempotent return the port's retry contract promises.
    """
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    cursor = ScriptedCursor(rows=[None], list_rows_sequence=[[], [_receipt_row(record)]])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    assert registry.register(record) == record
    assert len(cursor.executed) == 3
    assert connection.commit_count == 1


def test_register_reports_a_typed_conflict_for_a_concurrent_differing_registration() -> None:
    record = _record("instance-1").model_copy(update={"receipt": _receipt("postgres-docker:op-1")})
    winner = _record("instance-1").model_copy(update={"receipt": _receipt("postgres-docker:op-2")})
    cursor = ScriptedCursor(rows=[None], list_rows_sequence=[[], [_receipt_row(winner)]])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    with pytest.raises(InstanceRegistrationConflictError):
        registry.register(record)

    assert len(cursor.executed) == 3
    assert connection.commit_count == 0 and connection.rollback_count == 1


def test_register_is_idempotent_for_an_exact_committed_retry() -> None:
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    cursor = ScriptedCursor(list_rows=[_receipt_row(record)])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    assert registry.register(record) == record
    assert len(cursor.executed) == 1
    assert "SELECT" in cursor.executed[0][0]
    assert connection.commit_count == 1


def test_register_rejects_a_conflicting_reuse_of_the_operation_identity() -> None:
    record = _record("instance-1").model_copy(update={"receipt": _receipt()})
    conflicting = _record("instance-2").model_copy(update={"receipt": _receipt()})
    cursor = ScriptedCursor(list_rows=[_receipt_row(record)])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    with pytest.raises(InstanceRegistrationConflictError):
        registry.register(conflicting)

    assert len(cursor.executed) == 1
    assert connection.commit_count == 0 and connection.rollback_count == 1


def test_register_rejects_reuse_of_the_same_pointer_under_a_new_operation_id() -> None:
    original = _record("instance-1").model_copy(
        update={"receipt": _receipt("postgres-docker:op-1")}
    )
    reuse = _record("instance-1").model_copy(update={"receipt": _receipt("postgres-docker:op-2")})
    cursor = ScriptedCursor(list_rows=[_receipt_row(original)])
    connection = ScriptedConnection(cursor)
    registry = PostgresInstanceRegistry(ScriptedAcquirer(connection))

    with pytest.raises(InstanceRegistrationConflictError):
        registry.register(reuse)

    assert len(cursor.executed) == 1
    assert connection.commit_count == 0 and connection.rollback_count == 1
