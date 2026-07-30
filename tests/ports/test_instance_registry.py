from __future__ import annotations

import importlib
import inspect
import sys
from typing import get_type_hints

import pytest

from odoo_forge.instance_registry import (
    InstanceId,
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
)
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.resource_ownership import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId
from tests.instance_registry.test_contract import _trap_external_io


def _scope(project_id: str = "project-1") -> ProjectScope:
    return ProjectScope(tenant=TenantId(value="tenant-1"), project_id=project_id)


def _record(instance_id: str, project_id: str = "project-1") -> InstanceRecord:
    return InstanceRecord(
        pointer=InstancePointer(
            scope=_scope(project_id), instance_id=InstanceId(value=instance_id)
        ),
        resource=ResourceRef(
            identifier=f"resource-{instance_id}",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


class _ConformingInstanceRegistry:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], InstanceRecord] = {}

    def store(self, record: InstanceRecord) -> InstanceRecord:
        key = _key(record.pointer)
        self._records[key] = record
        return record

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        try:
            return self._records[_key(pointer)]
        except KeyError as exc:
            raise InstanceRecordNotFoundError(pointer) from exc

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        records = (record for record in self._records.values() if record.pointer.scope == scope)
        return tuple(sorted(records, key=lambda record: record.pointer.instance_id.value))


def _key(pointer: InstancePointer) -> tuple[str, str, str]:
    return (pointer.scope.tenant.value, pointer.scope.project_id, pointer.instance_id.value)


def test_conforming_registry_satisfies_runtime_checkable_protocol() -> None:
    assert isinstance(_ConformingInstanceRegistry(), InstanceRegistry)


def test_runtime_protocol_check_only_requires_operation_presence() -> None:
    class _IncompatibleOperationShapes:
        def store(self) -> None:
            return None

        def get(self) -> None:
            return None

        def list(self) -> None:
            return None

    assert isinstance(_IncompatibleOperationShapes(), InstanceRegistry)


def test_port_import_performs_no_external_io(monkeypatch: pytest.MonkeyPatch) -> None:
    _trap_external_io(monkeypatch)
    sys.modules.pop("odoo_forge.ports.instance_registry", None)

    port = importlib.import_module("odoo_forge.ports.instance_registry")

    assert port.InstanceRegistry.__module__ == "odoo_forge.ports.instance_registry"


def test_port_declares_exact_core_signatures_and_return_types() -> None:
    expected_parameters = {
        "store": ["self", "record"],
        "get": ["self", "pointer"],
        "list": ["self", "scope"],
    }
    expected_types = {
        "store": (InstanceRecord, InstanceRecord),
        "get": (InstancePointer, InstanceRecord),
        "list": (ProjectScope, tuple[InstanceRecord, ...]),
    }

    for name, parameters in expected_parameters.items():
        method = getattr(InstanceRegistry, name)
        assert list(inspect.signature(method).parameters) == parameters
        hints = get_type_hints(method)
        argument, result = expected_types[name]
        argument_name = parameters[1]
        assert hints[argument_name] is argument
        assert hints["return"] == result


def test_incomplete_registry_is_rejected_by_runtime_protocol_check() -> None:
    class _MissingList:
        def store(self, record: InstanceRecord) -> InstanceRecord:
            return record

        def get(self, pointer: InstancePointer) -> InstanceRecord:
            raise InstanceRecordNotFoundError(pointer)

    assert not isinstance(_MissingList(), InstanceRegistry)


def test_store_replaces_by_pointer_and_get_returns_authoritative_record() -> None:
    registry = _ConformingInstanceRegistry()
    original = _record("instance-1")
    replacement = _record("instance-1")
    replacement = replacement.model_copy(
        update={
            "resource": ResourceRef(
                identifier="replacement-resource",
                resource_kind="instance",
                ownership=ResourceOwnership.ADOPTED,
            )
        }
    )

    assert registry.store(original) == original
    assert registry.store(replacement) == replacement
    assert registry.get(original.pointer) == replacement


def test_list_returns_deterministic_tuple_for_scope_and_excludes_other_scopes() -> None:
    registry = _ConformingInstanceRegistry()
    registry.store(_record("zeta"))
    registry.store(_record("alpha"))
    registry.store(_record("other", project_id="project-2"))

    listed = registry.list(_scope())

    assert listed == (_record("alpha"), _record("zeta"))
    assert isinstance(listed, tuple)
    assert registry.list(_scope("project-without-records")) == ()


def test_get_raises_typed_not_found_error_for_missing_pointer() -> None:
    registry = _ConformingInstanceRegistry()
    pointer = _record("missing").pointer

    with pytest.raises(InstanceRecordNotFoundError) as excinfo:
        registry.get(pointer)

    assert excinfo.value.pointer == pointer
