"""Synchronous PostgreSQL persistence for the instance registry port."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, TypeVar, cast

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry import (
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
    InstanceRegistrationConflictError,
    MissingReceiptError,
)
from odoo_forge.instance_registry.types import InstanceId
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.resource_ownership import OwnershipReceipt, ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId

__all__ = ["Connection", "ConnectionAcquirer", "Cursor", "PostgresInstanceRegistry"]

_logger = logging.getLogger(__name__)


class Cursor(Protocol):
    def execute(self, query: str, parameters: tuple[object, ...]) -> object: ...

    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


ConnectionAcquirer = Callable[[], AbstractContextManager[Connection]]
_Result = TypeVar("_Result")

_COLUMNS = (
    "tenant_id, project_id, instance_id, resource_identifier, resource_kind, resource_ownership"
)
_STORE_SQL = f"""
INSERT INTO public.instance_registry ({_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (tenant_id, project_id, instance_id) DO UPDATE SET
    resource_identifier = EXCLUDED.resource_identifier,
    resource_kind = EXCLUDED.resource_kind,
    resource_ownership = EXCLUDED.resource_ownership,
    updated_at = now()
RETURNING {_COLUMNS}
"""
_GET_SQL = f"""
SELECT {_COLUMNS}
FROM public.instance_registry
WHERE tenant_id = %s AND project_id = %s AND instance_id = %s
"""
_LIST_SQL = f"""
SELECT {_COLUMNS}
FROM public.instance_registry
WHERE tenant_id = %s AND project_id = %s
ORDER BY instance_id ASC
"""
_RECEIPT_COLUMNS = (
    f"{_COLUMNS}, operation_id, request_digest, owned_resource_ids, live_proof_expected"
)
_REGISTER_LOOKUP_SQL = f"""
SELECT {_RECEIPT_COLUMNS}
FROM public.instance_registry
WHERE operation_id = %s OR (tenant_id, project_id, instance_id) = (%s, %s, %s)
"""
_REGISTER_INSERT_SQL = f"""
INSERT INTO public.instance_registry ({_RECEIPT_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING {_RECEIPT_COLUMNS}
"""


def _record_parameters(record: InstanceRecord) -> tuple[object, ...]:
    return (
        record.pointer.scope.tenant.value,
        record.pointer.scope.project_id,
        record.pointer.instance_id.value,
        record.resource.identifier,
        record.resource.resource_kind,
        record.resource.ownership.value,
    )


def _pointer_parameters(pointer: InstancePointer) -> tuple[object, ...]:
    return (
        pointer.scope.tenant.value,
        pointer.scope.project_id,
        pointer.instance_id.value,
    )


def _receipt_parameters(receipt: OwnershipReceipt) -> tuple[object, ...]:
    return (
        receipt.operation.operation_id,
        receipt.operation.request_digest,
        list(receipt.owned_resource_ids),
        receipt.live_proof_expected,
    )


def _receipt_record_parameters(
    record: InstanceRecord, receipt: OwnershipReceipt
) -> tuple[object, ...]:
    return (*_record_parameters(record), *_receipt_parameters(receipt))


def _record_from_receipt_row(row: tuple[object, ...]) -> InstanceRecord:
    *base_row, operation_id, request_digest, owned_resource_ids, live_proof_expected = row
    record = _record_from_row(tuple(base_row))
    receipt = OwnershipReceipt(
        operation=DurableOperationIdentity(
            operation_id=cast(str, operation_id), request_digest=cast(str, request_digest)
        ),
        owned_resource_ids=tuple(cast("list[str]", owned_resource_ids)),
        live_proof_expected=cast(bool, live_proof_expected),
    )
    return record.model_copy(update={"receipt": receipt})


def _record_from_row(row: tuple[object, ...]) -> InstanceRecord:
    tenant_id, project_id, instance_id, identifier, resource_kind, ownership = row
    return InstanceRecord(
        pointer=InstancePointer(
            scope=ProjectScope(
                tenant=TenantId(value=cast(str, tenant_id)),
                project_id=cast(str, project_id),
            ),
            instance_id=InstanceId(value=cast(str, instance_id)),
        ),
        resource=ResourceRef(
            identifier=cast(str, identifier),
            resource_kind=cast(str, resource_kind),
            ownership=ResourceOwnership(str(ownership)),
        ),
    )


class PostgresInstanceRegistry(InstanceRegistry):
    """Persist immutable instance records without owning the connection pool."""

    def __init__(self, acquire: ConnectionAcquirer) -> None:
        self._acquire = acquire

    def _transaction(self, operation: Callable[[Connection], _Result]) -> _Result:
        with self._acquire() as connection:
            try:
                result = operation(connection)
                connection.commit()
            except Exception:
                try:
                    connection.rollback()
                except Exception:
                    _logger.exception("Transaction rollback failed")
                raise
            return result

    def store(self, record: InstanceRecord) -> InstanceRecord:
        def operation(connection: Connection) -> InstanceRecord:
            cursor = connection.cursor()
            cursor.execute(_STORE_SQL, _record_parameters(record))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("store did not return an authoritative row")
            return _record_from_row(row)

        return self._transaction(operation)

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        def operation(connection: Connection) -> InstanceRecord:
            cursor = connection.cursor()
            cursor.execute(_GET_SQL, _pointer_parameters(pointer))
            row = cursor.fetchone()
            if row is None:
                raise InstanceRecordNotFoundError(pointer)
            return _record_from_row(row)

        return self._transaction(operation)

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        def operation(connection: Connection) -> tuple[InstanceRecord, ...]:
            cursor = connection.cursor()
            cursor.execute(_LIST_SQL, (scope.tenant.value, scope.project_id))
            return tuple(_record_from_row(row) for row in cursor.fetchall())

        return self._transaction(operation)

    def register(self, record: InstanceRecord) -> InstanceRecord:
        receipt = record.receipt
        if receipt is None:
            raise MissingReceiptError(record.pointer)

        def operation(connection: Connection) -> InstanceRecord:
            cursor = connection.cursor()
            cursor.execute(
                _REGISTER_LOOKUP_SQL,
                (receipt.operation.operation_id, *_pointer_parameters(record.pointer)),
            )
            rows = cursor.fetchall()
            for row in rows:
                existing = _record_from_receipt_row(row)
                if existing == record:
                    return existing
            if rows:
                raise InstanceRegistrationConflictError(record.pointer)
            cursor.execute(_REGISTER_INSERT_SQL, _receipt_record_parameters(record, receipt))
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("register did not return an authoritative row")
            return _record_from_receipt_row(inserted)

        return self._transaction(operation)
