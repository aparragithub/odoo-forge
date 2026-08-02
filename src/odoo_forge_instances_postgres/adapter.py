"""Synchronous PostgreSQL persistence for the instance registry port."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from typing import Protocol, TypeVar, cast

from odoo_forge.instance_registry import (
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
)
from odoo_forge.instance_registry.types import InstanceId
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.resource_ownership import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId

__all__ = ["Connection", "ConnectionAcquirer", "Cursor", "PostgresInstanceRegistry"]


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
                with suppress(Exception):
                    connection.rollback()
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
