"""Deterministic in-memory implementations of the instance registry port."""

from __future__ import annotations

from odoo_forge.instance_registry import (
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
    InstanceRegistrationConflictError,
    MissingReceiptError,
)
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.tenancy import ProjectScope


class FakeInstanceRegistry(InstanceRegistry):
    """Store instance records in isolated, process-local memory."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], InstanceRecord] = {}
        self._by_operation: dict[str, InstanceRecord] = {}

    def store(self, record: InstanceRecord) -> InstanceRecord:
        key = (
            record.pointer.scope.tenant.value,
            record.pointer.scope.project_id,
            record.pointer.instance_id.value,
        )
        self._records[key] = record
        return self._records[key]

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        key = (
            pointer.scope.tenant.value,
            pointer.scope.project_id,
            pointer.instance_id.value,
        )
        try:
            return self._records[key]
        except KeyError:
            raise InstanceRecordNotFoundError(pointer) from None

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        records = (
            record
            for (tenant, project, _), record in self._records.items()
            if tenant == scope.tenant.value and project == scope.project_id
        )
        return tuple(sorted(records, key=lambda record: record.pointer.instance_id.value))

    def register(self, record: InstanceRecord) -> InstanceRecord:
        if record.receipt is None:
            raise MissingReceiptError(record.pointer)
        operation_id = record.receipt.operation.operation_id
        key = (
            record.pointer.scope.tenant.value,
            record.pointer.scope.project_id,
            record.pointer.instance_id.value,
        )
        existing = self._by_operation.get(operation_id) or self._records.get(key)
        if existing is not None:
            if existing == record:
                return existing
            raise InstanceRegistrationConflictError(record.pointer)
        self._by_operation[operation_id] = record
        self._records[key] = record
        return record


__all__ = ["FakeInstanceRegistry"]
