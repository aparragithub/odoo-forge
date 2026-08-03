import builtins
import importlib
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry import (
    InstanceId,
    InstancePointer,
    InstanceRecord,
    InstanceRecordNotFoundError,
    InstanceRegistrationConflictError,
    InstanceRegistryError,
    MissingReceiptError,
)
from odoo_forge.resource_ownership import OwnershipReceipt, ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId


def _scope() -> ProjectScope:
    return ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")


def _pointer(value: str = "instance-1") -> InstancePointer:
    return InstancePointer(scope=_scope(), instance_id=InstanceId(value=value))


def _record() -> InstanceRecord:
    return InstanceRecord(
        pointer=_pointer(),
        resource=ResourceRef(
            identifier="resource-1",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def _receipt(operation_id: str = "postgres-docker:op-1") -> OwnershipReceipt:
    return OwnershipReceipt(
        operation=DurableOperationIdentity(operation_id=operation_id, request_digest="a" * 64),
        owned_resource_ids=("container-1",),
    )


def _trap_external_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("external I/O attempted by the pure-domain contract")

    for owner, name in (
        (Path, "open"),
        (Path, "read_text"),
        (Path, "write_text"),
        (socket, "socket"),
        (socket, "create_connection"),
        (subprocess, "run"),
        (subprocess, "Popen"),
        (sqlite3, "connect"),
    ):
        monkeypatch.setattr(owner, name, fail)

    real_import = builtins.__import__
    forbidden_frameworks = {"django", "flask", "fastapi", "odoo", "sqlalchemy"}

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".", 1)[0] in forbidden_frameworks:
            raise AssertionError(f"framework import attempted: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def test_instance_values_are_immutable_and_compose_existing_core_values() -> None:
    record = _record()

    assert record.pointer.scope == _scope()
    assert record.pointer.instance_id == InstanceId(value="instance-1")
    assert record.resource.resource_kind == "instance"
    with pytest.raises(ValidationError):
        cast(Any, record.pointer.instance_id).value = "changed"
    with pytest.raises(ValidationError):
        cast(Any, record).resource = record.resource


def test_instance_values_reject_empty_and_unknown_input_without_leaking_hidden_values() -> None:
    with pytest.raises(ValidationError) as excinfo:
        InstanceId(value="", hidden_marker="secret-marker")  # type: ignore[call-arg]

    assert "secret-marker" not in str(excinfo.value)

    with pytest.raises(ValidationError):
        InstancePointer(scope=_scope(), instance_id=InstanceId(value="instance-1"), extra="nope")  # type: ignore[call-arg]


def test_domain_import_and_construction_perform_no_external_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trap_external_io(monkeypatch)
    for module_name in (
        "odoo_forge.instance_registry",
        "odoo_forge.instance_registry.errors",
        "odoo_forge.instance_registry.types",
    ):
        sys.modules.pop(module_name, None)

    domain = importlib.import_module("odoo_forge.instance_registry")
    record = domain.InstanceRecord(
        pointer=domain.InstancePointer(
            scope=_scope(), instance_id=domain.InstanceId(value="imported")
        ),
        resource=_record().resource,
    )

    assert record.pointer.instance_id.value == "imported"


def test_instance_record_rejects_invalid_composed_resource() -> None:
    with pytest.raises(ValidationError):
        InstanceRecord(pointer=_pointer(), resource={"identifier": "resource-1"})  # type: ignore[arg-type]


def test_instance_record_defaults_to_no_receipt_and_accepts_lineage_evidence() -> None:
    bare = _record()
    assert bare.receipt is None

    lineage = _record().model_copy(update={"receipt": _receipt()})
    assert lineage.receipt == _receipt()
    with pytest.raises(ValidationError):
        cast(Any, lineage).receipt = _receipt("postgres-docker:op-2")


def test_instance_registry_exports_only_the_public_domain_contract() -> None:
    instance_registry = importlib.import_module("odoo_forge.instance_registry")

    assert set(instance_registry.__all__) == {
        "InstanceId",
        "InstancePointer",
        "InstanceRecord",
        "InstanceRecordNotFoundError",
        "InstanceRegistrationConflictError",
        "InstanceRegistryError",
        "MissingReceiptError",
        "ReceiptOverwriteRejectedError",
    }
    assert all(
        "image" not in name.lower() and "ghcr" not in name.lower()
        for name in instance_registry.__all__
    )


def test_not_found_error_is_typed_and_redacts_unrelated_input() -> None:
    error = InstanceRecordNotFoundError(_pointer("private-instance"))

    assert isinstance(error, InstanceRegistryError)
    assert error.pointer == _pointer("private-instance")
    assert str(error) == "instance record not found: project-1/private-instance"


def test_missing_receipt_error_is_typed() -> None:
    error = MissingReceiptError(_pointer("private-instance"))

    assert isinstance(error, InstanceRegistryError)
    assert error.pointer == _pointer("private-instance")
    assert str(error) == "registration receipt required: project-1/private-instance"


def test_registration_conflict_error_is_typed() -> None:
    error = InstanceRegistrationConflictError(_pointer("private-instance"))

    assert isinstance(error, InstanceRegistryError)
    assert error.pointer == _pointer("private-instance")
    assert str(error) == "instance registration conflict: project-1/private-instance"
