"""Runtime and exact-signature conformance evidence for registry implementations."""

from __future__ import annotations

import inspect
from contextlib import AbstractContextManager

import pytest

from odoo_forge.instance_registry import InstancePointer, InstanceRecord
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.tenancy import ProjectScope
from odoo_forge_instances_postgres.adapter import (
    Connection,
    PostgresInstanceRegistry,
)
from odoo_forge_instances_postgres.fakes import FakeInstanceRegistry

_CONTRACT_METHODS = {"store", "get", "list"}


def _no_live_connection() -> AbstractContextManager[Connection]:
    raise AssertionError("the conformance suite must not acquire a live PostgreSQL connection")


def _public_methods(candidate_type: type[object]) -> set[str]:
    return {
        name
        for base in candidate_type.__mro__
        for name, member in vars(base).items()
        if not name.startswith("_") and callable(member)
    }


def _assert_exact_conformance(candidate_type: type[object]) -> None:
    assert _public_methods(candidate_type) == _CONTRACT_METHODS

    for method_name in _CONTRACT_METHODS:
        candidate_method = getattr(candidate_type, method_name)
        contract_method = getattr(InstanceRegistry, method_name)
        assert inspect.signature(candidate_method) == inspect.signature(contract_method)
        assert not inspect.iscoroutinefunction(candidate_method)


@pytest.mark.parametrize(
    "candidate",
    [
        FakeInstanceRegistry(),
        PostgresInstanceRegistry(_no_live_connection),
    ],
    ids=["fake", "postgres-adapter"],
)
def test_fake_and_postgres_adapter_conform_without_database_access(candidate: object) -> None:
    assert isinstance(candidate, InstanceRegistry)
    _assert_exact_conformance(type(candidate))


class MissingMethod:
    def store(self, record: InstanceRecord) -> InstanceRecord:
        return record

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        raise AssertionError(pointer)


class WrongSignature:
    def store(self, record: object) -> object:
        return record

    def get(self, pointer: object) -> object:
        return pointer

    def list(self, scope: object) -> tuple[object, ...]:
        return (scope,)


class AsyncRegistry:
    async def store(self, record: InstanceRecord) -> InstanceRecord:
        return record

    async def get(self, pointer: InstancePointer) -> InstanceRecord:
        raise AssertionError(pointer)

    async def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        return ()


class Resettable:
    def reset(self) -> None:
        return None


class InheritedExtraMethod(Resettable):
    def store(self, record: InstanceRecord) -> InstanceRecord:
        return record

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        raise AssertionError(pointer)

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        return ()


def test_missing_protocol_method_is_rejected_by_runtime_conformance() -> None:
    assert not isinstance(MissingMethod(), InstanceRegistry)


@pytest.mark.parametrize("candidate_type", [WrongSignature, AsyncRegistry, InheritedExtraMethod])
def test_signature_drift_is_rejected_after_structural_runtime_check(
    candidate_type: type[object],
) -> None:
    candidate = candidate_type()

    assert isinstance(candidate, InstanceRegistry)
    with pytest.raises(AssertionError):
        _assert_exact_conformance(candidate_type)
