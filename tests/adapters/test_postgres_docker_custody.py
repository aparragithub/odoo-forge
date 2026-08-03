# fmt: off
import json
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from pydantic import ValidationError

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.ports.resource_custody import (
    CustodyRequest,
    CustodyStartingState,
    CustodyTransition,
    CustodyTransitionConflictError,
    CustodyUnverifiableError,
    custody_request_digest,
)
from odoo_forge.resource_ownership.types import ResourceOwnership, ResourceRef
from odoo_forge.tenancy.types import ProjectScope, TenantId
from odoo_forge_postgres_docker.authority import (
    DockerResourceCustodyAdapter,
    LocalOwnershipAuthority,
)

_EXPECTED_DIGEST = "1e340b7568efdcbdfdb4282c083a3c93b2257fd7352defcb45c0bc46c3d7156c"
_POINTER = InstancePointer(
    scope=ProjectScope(tenant=TenantId(value="tenant-a"), project_id="project-a"),
    instance_id=InstanceId(value="instance-a"),
)

def _request(
    operation: str = "postgres-docker:op-a",
    resource_id: str = "immutable-a",
    *,
    resource_name: str = "database-a",
    resource_kind: str = "container",
    ownership: ResourceOwnership = ResourceOwnership.CREATED,
    request_digest: str | None = None,
) -> CustodyRequest:
    resource = ResourceRef(identifier="database-a", resource_kind=resource_kind, ownership=ownership)  # noqa: E501
    digest = request_digest or custody_request_digest(
        pointer=_POINTER,
        resource=resource,
        resource_name=resource_name,
        resource_id=resource_id,
        starting_state=CustodyStartingState.UNRESERVED,
        requested_transition=CustodyTransition.RESERVE_BIND_ACTIVATE,
    )
    return CustodyRequest(
        operation=DurableOperationIdentity(operation_id=operation, request_digest=digest),
        pointer=_POINTER,
        resource=resource,
        resource_name=resource_name,
        resource_id=resource_id,
        starting_state=CustodyStartingState.UNRESERVED,
        requested_transition=CustodyTransition.RESERVE_BIND_ACTIVATE,
    )

@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"operation": "not-postgres"}, "unsupported custody operation"),
        ({"operation": ""}, "at least 1 character"),
        ({"operation": "postgres-docker:"}, "custody operation token is required"),
        ({"operation": "postgres-docker: "}, "custody operation token is required"),
        ({"resource_name": "other-name"}, "custody resource name must match"),
        ({"request_digest": "wrong-digest"}, "custody request digest does not match"),
        ({"resource_kind": "volume"}, "unsupported custody resource"),
        ({"ownership": ResourceOwnership.EXTERNAL}, "unsupported custody resource"),
    ],
)
def test_request_contract_rejects_invalid_identity_and_resource(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _request(**changes)

def _inspect(request: CustodyRequest, *, labels: dict[str, str] | object = "valid") -> str:
    actual = {
        "io.odoo-forge.provider": "postgres-docker",
        "io.odoo-forge.operation": request.operation.operation_id,
        "io.odoo-forge.resource-kind": "container",
        "io.odoo-forge.creator-token": request.operation.operation_id.removeprefix("postgres-docker:"),  # noqa: E501
    }
    if labels == "not-json":
        return "not-json"
    return json.dumps([{"Id": request.resource_id, "Config": {"Labels": actual if labels == "valid" else labels}}])  # noqa: E501


def _adapter(
    authority: LocalOwnershipAuthority, request: CustodyRequest, payload: object = "valid"
) -> DockerResourceCustodyAdapter:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        assert list(argv) == ["docker", "inspect", request.resource_name]
        if isinstance(payload, BaseException):
            raise payload
        return subprocess.CompletedProcess(argv, 0, _inspect(request, labels=payload), "")
    return DockerResourceCustodyAdapter(authority, runner=runner, timeout=3.0)


@pytest.mark.parametrize("payload", ["not-json", "{}", "[]", [{"wrong": "shape"}], {"bad": "labels"}, {"x": 1}])  # noqa: E501
def test_malformed_inspect_and_labels_are_unverifiable(tmp_path: Path, payload: object) -> None:
    request, authority = _request(), LocalOwnershipAuthority(tmp_path / "authority")
    with pytest.raises(CustodyUnverifiableError):
        _adapter(authority, request, payload).confirm(request)
    assert not (authority.root / "authority.json").exists()


def test_timeout_and_immutable_id_mismatch_are_unverifiable(tmp_path: Path) -> None:
    request, authority = _request(), LocalOwnershipAuthority(tmp_path / "authority")
    with pytest.raises(CustodyUnverifiableError):
        _adapter(authority, request, subprocess.TimeoutExpired("docker inspect", 3.0)).confirm(request)  # noqa: E501
    mismatch = _adapter(authority, request)
    mismatch._runner = lambda argv, *, timeout: subprocess.CompletedProcess(
        argv, 0, _inspect(request).replace(request.resource_id, "other-id"), ""
    )
    with pytest.raises(CustodyUnverifiableError):
        mismatch.confirm(request)


@pytest.mark.parametrize("seed", ["absent", "reserved-empty", "reserved-same", "active-same"])
def test_supported_states_converge_without_duplicate_transitions(tmp_path: Path, seed: str) -> None:
    request, authority = _request(), LocalOwnershipAuthority(tmp_path / "authority")
    assert request.operation.request_digest == _EXPECTED_DIGEST
    if seed != "absent":
        authority.reserve(request.operation.operation_id, request.resource_name)
    if seed in {"reserved-same", "active-same"}:
        authority.bind(request.operation.operation_id, request.resource_name, request.resource_id)
    if seed == "active-same":
        authority.activate(request.operation.operation_id, request.resource_name, request.resource_id)  # noqa: E501
    receipt = _adapter(authority, request).confirm(request)
    assert receipt.operation == request.operation
    assert receipt.owned_resource_ids == (request.resource_id,)
    assert len(authority.read()["records"]) == 3


@pytest.mark.parametrize(
    ("operation", "state"), [("postgres-docker:other", "active"), ("postgres-docker:op-a", "retired")]  # noqa: E501
)
def test_conflicting_state_and_operation_fail_closed(tmp_path: Path, operation: str, state: str) -> None:  # noqa: E501
    request, authority = _request(), LocalOwnershipAuthority(tmp_path / "authority")
    _write_record(authority, request, operation=operation, state=state)
    with pytest.raises(CustodyTransitionConflictError):
        _adapter(authority, request).confirm(request)


def _write_record(authority, request, *, operation=None, docker_id=None, state):
    authority.write({"operation": operation or request.operation.operation_id, "kind": "container", "name": request.resource_name, "docker_id": docker_id or request.resource_id, "state": state})  # noqa: E501


@pytest.mark.parametrize("state", ["reserved", "active"])
def test_same_operation_different_docker_id_conflicts_without_mutation(tmp_path: Path, state: str) -> None:  # noqa: E501
    request, authority = _request(), LocalOwnershipAuthority(tmp_path / "authority")
    _write_record(authority, request, docker_id="immutable-old", state=state)
    before = authority.read()
    with pytest.raises(CustodyTransitionConflictError):
        _adapter(authority, request).confirm(request)
    assert authority.read() == before


def test_concurrent_exact_retries_commit_one_transition_sequence(tmp_path: Path) -> None:
    request, authority = _request(), LocalOwnershipAuthority(tmp_path / "authority")
    barrier = Barrier(2)
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        barrier.wait(timeout=2)
        return subprocess.CompletedProcess(argv, 0, _inspect(request), "")
    adapter = DockerResourceCustodyAdapter(authority, runner=runner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(adapter.confirm, (request, request)))
    assert receipts[0] == receipts[1]
    assert len(authority.read()["records"]) == 3
# fmt: on
