from __future__ import annotations

import pytest

from odoo_forge.control_plane.authority import (
    ControlPlaneAuthority,
    RegistrationRequest,
    RegistrationValidationError,
)
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry import (
    InstanceRecord,
    InstanceRecordNotFoundError,
    InstanceRegistrationConflictError,
)
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.ports.resource_custody import (
    CustodyRequest,
    CustodyStartingState,
    CustodyTransition,
    CustodyTransitionConflictError,
    CustodyUnverifiableError,
    custody_request_digest,
)
from odoo_forge.resource_ownership.types import OwnershipReceipt, ResourceOwnership, ResourceRef
from odoo_forge.tenancy.types import ProjectScope, TenantId
from odoo_forge_instances_postgres.fakes import FakeInstanceRegistry

_POINTER = InstancePointer(
    scope=ProjectScope(tenant=TenantId(value="tenant-a"), project_id="project-a"),
    instance_id=InstanceId(value="instance-a"),
)
_RESOURCE = ResourceRef(
    identifier="database-a", resource_kind="container", ownership=ResourceOwnership.CREATED
)


def _request(
    operation: str = "postgres-docker:op-a",
    resource_id: str = "immutable-a",
    *,
    resource: ResourceRef = _RESOURCE,
    request_digest: str | None = None,
) -> RegistrationRequest:
    digest = request_digest or custody_request_digest(
        operation_id=operation,
        pointer=_POINTER,
        resource=resource,
        resource_name=resource.identifier,
        resource_id=resource_id,
        starting_state=CustodyStartingState.UNRESERVED,
        requested_transition=CustodyTransition.RESERVE_BIND_ACTIVATE,
    )
    return RegistrationRequest(
        operation=DurableOperationIdentity(operation_id=operation, request_digest=digest),
        pointer=_POINTER,
        resource=resource,
        resource_name=resource.identifier,
        resource_id=resource_id,
    )


class _FakeCustody:
    def __init__(
        self, *, error: Exception | None = None, receipt: OwnershipReceipt | None = None
    ) -> None:
        self.calls: list[CustodyRequest] = []
        self._error = error
        self._receipt = receipt

    def confirm(self, request: CustodyRequest) -> OwnershipReceipt:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        if self._receipt is not None:
            return self._receipt
        return OwnershipReceipt(
            operation=request.operation,
            owned_resource_ids=(request.resource_id,),
            live_proof_expected=True,
        )


class _FlakyRegistry:
    """Wrap a real fake registry, failing `register()` itself `failures` times."""

    def __init__(self, inner: FakeInstanceRegistry, *, failures: int) -> None:
        self._inner = inner
        self._remaining_failures = failures
        self.register_calls = 0

    def store(self, record: InstanceRecord) -> InstanceRecord:
        return self._inner.store(record)

    def get(self, pointer: InstancePointer) -> InstanceRecord:
        return self._inner.get(pointer)

    def list(self, scope: ProjectScope) -> tuple[InstanceRecord, ...]:
        return self._inner.list(scope)

    def register(self, record: InstanceRecord) -> InstanceRecord:
        self.register_calls += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise RuntimeError("transient commit failure")
        return self._inner.register(record)


class _AmbiguouslyCommittingRegistry(_FlakyRegistry):
    """Commit the row and THEN fail, the ambiguous external-call outcome.

    A connection dropped after a successful write looks like a failure to the
    caller while the row is already present, so the retry collides with the
    request's own committed row.
    """

    def register(self, record: InstanceRecord) -> InstanceRecord:
        self.register_calls += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            self._inner.register(record)
            raise RuntimeError("connection dropped after the row was committed")
        return self._inner.register(record)


def test_meaning_mismatch_is_rejected_without_touching_custody_or_registry() -> None:
    request = _request(request_digest="wrong-digest")
    custody = _FakeCustody()
    registry = FakeInstanceRegistry()

    with pytest.raises(RegistrationValidationError):
        ControlPlaneAuthority(custody, registry).register(request)

    assert custody.calls == []
    with pytest.raises(InstanceRecordNotFoundError):
        registry.get(request.pointer)


@pytest.mark.parametrize("error", [CustodyTransitionConflictError(), CustodyUnverifiableError()])
def test_custody_failure_is_fail_closed_and_writes_no_registry_row(error: Exception) -> None:
    request = _request()
    custody = _FakeCustody(error=error)
    registry = FakeInstanceRegistry()

    with pytest.raises(type(error)):
        ControlPlaneAuthority(custody, registry).register(request)

    with pytest.raises(InstanceRecordNotFoundError):
        registry.get(request.pointer)


def test_accepted_scoped_registration_persists_the_canonical_record() -> None:
    request = _request()
    custody = _FakeCustody()

    result = ControlPlaneAuthority(custody, FakeInstanceRegistry()).register(request)

    assert result.pointer == request.pointer
    assert result.resource == request.resource
    assert len(custody.calls) == 1


def test_lineage_evidence_is_visible_on_the_committed_record() -> None:
    request = _request()
    custody = _FakeCustody()

    result = ControlPlaneAuthority(custody, FakeInstanceRegistry()).register(request)

    assert result.receipt is not None
    assert result.receipt.operation == request.operation
    assert result.receipt.owned_resource_ids == (request.resource_id,)


def test_equivalent_retry_returns_existing_row_without_a_second_custody_confirmation() -> None:
    request = _request()
    custody = _FakeCustody()
    authority = ControlPlaneAuthority(custody, FakeInstanceRegistry())

    first = authority.register(request)
    second = authority.register(request)

    assert first == second
    assert len(custody.calls) == 1


def test_conflicting_retry_is_rejected_without_mutating_committed_state() -> None:
    request = _request()
    conflicting = _request(
        resource=ResourceRef(
            identifier="database-b", resource_kind="container", ownership=ResourceOwnership.CREATED
        )
    )
    custody = _FakeCustody()
    authority = ControlPlaneAuthority(custody, FakeInstanceRegistry())

    accepted = authority.register(request)
    with pytest.raises(InstanceRegistrationConflictError):
        authority.register(conflicting)

    assert authority.register(request) == accepted
    assert len(custody.calls) == 1


def test_commit_failure_after_custody_success_retries_the_registry_write_once() -> None:
    request = _request()
    custody = _FakeCustody()
    registry = _FlakyRegistry(FakeInstanceRegistry(), failures=1)

    result = ControlPlaneAuthority(custody, registry).register(request)

    assert result.pointer == request.pointer
    assert registry.register_calls == 2
    assert len(custody.calls) == 1


def test_retry_after_an_ambiguous_commit_converges_instead_of_conflicting() -> None:
    """An already-landed write must not surface as a conflict on retry.

    The first attempt commits and then reports failure, so the retry collides
    with the request's own row. That is evidence of success, not of a
    competing registration.
    """
    request = _request()
    custody = _FakeCustody()
    registry = _AmbiguouslyCommittingRegistry(FakeInstanceRegistry(), failures=1)

    result = ControlPlaneAuthority(custody, registry).register(request)

    assert result.pointer == request.pointer
    assert result.receipt is not None
    assert registry.register_calls == 2
    assert len(custody.calls) == 1
    assert len(registry.list(request.pointer.scope)) == 1


def test_persistent_commit_failure_propagates_after_one_bounded_retry() -> None:
    request = _request()
    custody = _FakeCustody()
    registry = _FlakyRegistry(FakeInstanceRegistry(), failures=2)

    with pytest.raises(RuntimeError):
        ControlPlaneAuthority(custody, registry).register(request)

    assert registry.register_calls == 2
    assert len(custody.calls) == 1
