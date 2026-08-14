from typing import cast

import pytest

import odoo_forge.deployment_spec.types as deployment_types
import odoo_forge.exposure.types as exposure_types
from odoo_forge.backend.plan import BackendPlan, ContainerSpec, NetworkSpec
from odoo_forge.backend.status import InstanceRef
from odoo_forge.durable_operations.service import build_terminal_commit, save_checkpoint
from odoo_forge.durable_operations.types import (
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
)
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.ports.durable_operation_store import DurableOperationRecord, DurableOperationStore
from odoo_forge.remote_deployment import (
    RemoteDeploymentCoordinator,
    RemoteDeploymentIncompleteError,
    RemoteDeploymentReceipt,
    RemoteDeploymentRequest,
    RemoteTargetFingerprint,
)
from odoo_forge.resource_ownership.types import (
    OwnershipReceipt,
    OwnershipRecord,
    ResourceOwnership,
    ResourceRef,
)
from odoo_forge.tenancy.types import ProjectScope, TenantId

SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
POINTER = InstancePointer(scope=SCOPE, instance_id=InstanceId(value="one"))
TARGET = RemoteTargetFingerprint(host="vps.example", user="deploy", port=22, host_key="ssh-ed25519")
RUN = DurableOperationIdentity(operation_id="run-1", request_digest="run-digest")
EXPOSURE = DurableOperationIdentity(operation_id="exposure-1", request_digest="exposure-digest")
REVISION = OperationRevision(value=1)


def owner(operation: DurableOperationIdentity, identifier: str) -> OwnershipRecord:
    return OwnershipRecord(
        ref=ResourceRef(
            identifier=identifier, resource_kind="container", ownership=ResourceOwnership.CREATED
        ),
        receipt=OwnershipReceipt(operation=operation, owned_resource_ids=(identifier,)),
    )


def deployment(exposed: bool = False) -> deployment_types.DeploymentSpec:
    return deployment_types.DeploymentSpec(
        pointer=POINTER,
        resource=ResourceRef(
            identifier="odoo-forge-project-1-one",
            resource_kind="network",
            ownership=ResourceOwnership.CREATED,
        ),
        runtime=deployment_types.OdooRuntimeIntent(odoo_version="18.0"),
        exposure=deployment_types.ExposureIntent(
            hostname="one.example",
            protocol=deployment_types.RouteProtocol.HTTP,
            dns=deployment_types.RequirementPolicy.REQUIRED,
            tls=deployment_types.RequirementPolicy.DISABLED,
        )
        if exposed
        else None,
    )


def plan() -> BackendPlan:
    network = NetworkSpec(name="odoo-forge-project-1-one", labels={"managed": "true"})
    common = {"network": network.name, "env": {}, "labels": {}}
    db, odoo = (
        ContainerSpec.model_validate(
            {"name": "db-one", "image": "postgres:16", "role": "postgres", **common}
        ),
        ContainerSpec.model_validate(
            {"name": "odoo-one", "image": "odoo-forge-odoo:18.0", "role": "odoo", **common}
        ),
    )
    return BackendPlan(network=network, volumes=[], postgres=db, odoo=odoo)


def request(
    exposed: bool = False,
    exposure_operation: DurableOperationIdentity = EXPOSURE,
) -> RemoteDeploymentRequest:
    return RemoteDeploymentRequest(
        deployment=deployment(exposed),
        plan=plan(),
        target=TARGET,
        runtime_operation=RUN,
        exposure_operation=exposure_operation if exposed else None,
        runtime_ownership=(owner(RUN, "odoo-one"),),
    )


def record(operation: DurableOperationIdentity, outcome: LifecycleState) -> DurableOperationRecord:
    evidence = RedactedEvidence(event="terminal", summary="operation reached terminal state")
    return DurableOperationRecord(
        operation,
        OperationRevision(value=2),
        outcome,
        save_checkpoint(OperationRevision(value=0), "ready", evidence),
        build_terminal_commit(OperationRevision(value=1), outcome, (evidence,), ()),
        (evidence,),
    )


class Store(dict[str, DurableOperationRecord]):
    def create_or_load(self, operation: DurableOperationIdentity) -> DurableOperationRecord:
        return self[operation.operation_id]


class Runtime:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[BackendPlan] = []

    def run(self, value: BackendPlan) -> InstanceRef:
        self.calls.append(value)
        if self.error:
            raise self.error
        return InstanceRef(
            project="project-1",
            instance="one",
            network="odoo-forge-project-1-one",
            postgres_container="db-one",
            odoo_container="odoo-one",
        )


class Exposure:
    def __init__(self, result: exposure_types.ExposureResult) -> None:
        self.result = result
        self.requests: list[exposure_types.ExposureRequest] = []

    def reconcile(self, request: exposure_types.ExposureRequest) -> exposure_types.ExposureResult:
        self.requests.append(request)
        return self.result


class FailingExposure:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def reconcile(self, request: exposure_types.ExposureRequest) -> exposure_types.ExposureResult:
        raise self.error


def coordinator(
    runtime: Runtime,
    store: Store,
    recorded: list[RemoteDeploymentReceipt] | None = None,
    exposure: Exposure | FailingExposure | None = None,
) -> RemoteDeploymentCoordinator:
    return RemoteDeploymentCoordinator(
        runtime_provider=runtime,
        operation_store=cast(DurableOperationStore, store),
        recorder=(recorded if recorded is not None else []).append,
        exposure_provider=exposure,
    )


def test_success_receipt_preserves_target_label_and_runtime_ownership() -> None:
    recorded: list[RemoteDeploymentReceipt] = []
    runtime, store = Runtime(), Store({"run-1": record(RUN, LifecycleState.SUCCEEDED)})
    receipt = coordinator(runtime, store, recorded).deploy(request())
    assert (receipt.provider, receipt.target, receipt.runtime_operation) == ("vps", TARGET, RUN)
    assert (receipt.runtime_ownership, receipt.exposure_ownership) == (
        (owner(RUN, "odoo-one"),),
        (),
    )
    assert receipt.outcome is LifecycleState.SUCCEEDED and recorded == [receipt]


def test_exposure_uses_empty_input_and_operation_matched_ownership() -> None:
    route = owner(EXPOSURE, "route-one")
    result = exposure_types.ExposureResult(
        operation=EXPOSURE,
        outcome=exposure_types.ExposureOutcome.READY,
        routing_status=exposure_types.ExposureCheckStatus.VERIFIED,
        dns_status=exposure_types.ExposureCheckStatus.VERIFIED,
        ready=True,
        ownership=(route,),
    )
    store = Store(
        {
            "run-1": record(RUN, LifecycleState.SUCCEEDED),
            "exposure-1": record(EXPOSURE, LifecycleState.SUCCEEDED),
        }
    )
    exposure, req = Exposure(result), request(True)
    receipt = coordinator(Runtime(), store, exposure=exposure).deploy(req)
    assert exposure.requests[0].ownership == () and exposure.requests[0].operation == EXPOSURE
    assert receipt.runtime_ownership != receipt.exposure_ownership == (route,)


def test_in_progress_exposure_fails_closed_without_receipt() -> None:
    result = exposure_types.ExposureResult(
        operation=EXPOSURE, outcome=exposure_types.ExposureOutcome.IN_PROGRESS
    )
    pending = DurableOperationRecord(EXPOSURE, REVISION, LifecycleState.IN_PROGRESS)
    store = Store({"run-1": record(RUN, LifecycleState.SUCCEEDED), "exposure-1": pending})
    recorded: list[RemoteDeploymentReceipt] = []
    with pytest.raises(RemoteDeploymentIncompleteError):
        coordinator(Runtime(), store, recorded, Exposure(result)).deploy(request(True))
    assert recorded == []


def test_same_runtime_and_exposure_operation_is_rejected_before_provider_call() -> None:
    with pytest.raises(RemoteDeploymentIncompleteError):
        coordinator((runtime := Runtime()), Store({})).deploy(request(True, exposure_operation=RUN))
    assert runtime.calls == []


def test_adapter_failure_records_failed_evidence_and_reraises_same_exception() -> None:
    error, failed = RuntimeError("adapter failure"), record(RUN, LifecycleState.FAILED)
    recorded: list[RemoteDeploymentReceipt] = []
    with pytest.raises(RuntimeError) as raised:
        coordinator(Runtime(error), Store({"run-1": failed}), recorded).deploy(request())
    assert (
        raised.value is error
        and len(recorded) == 1
        and recorded[0].outcome is LifecycleState.FAILED
    )


def test_exposure_failure_records_exact_failed_lineage_and_reraises_same_exception() -> None:
    error = RuntimeError("exposure failure")
    failed_exposure = record(EXPOSURE, LifecycleState.FAILED)
    store = Store({"run-1": record(RUN, LifecycleState.SUCCEEDED), "exposure-1": failed_exposure})
    recorded: list[RemoteDeploymentReceipt] = []
    with pytest.raises(RuntimeError) as raised:
        coordinator(Runtime(), store, recorded, FailingExposure(error)).deploy(request(True))

    receipt = recorded[0]
    assert raised.value is error
    assert (
        receipt.deployment,
        receipt.provider,
        receipt.target,
        receipt.runtime_operation,
        receipt.runtime_ownership,
        receipt.exposure_operation,
        receipt.exposure_result,
        receipt.exposure_ownership,
        receipt.exposure_terminal_record,
        receipt.outcome,
    ) == (
        deployment(True),
        "vps",
        TARGET,
        RUN,
        (owner(RUN, "odoo-one"),),
        EXPOSURE,
        None,
        (),
        failed_exposure,
        LifecycleState.FAILED,
    )


@pytest.mark.parametrize(
    "exposure_record",
    [
        None,
        DurableOperationRecord(EXPOSURE, REVISION, LifecycleState.IN_PROGRESS),
        record(RUN, LifecycleState.FAILED),
    ],
)
def test_invalid_exposure_failure_evidence_records_no_receipt(
    exposure_record: DurableOperationRecord | None,
) -> None:
    error = RuntimeError("exposure failure")
    records = {"run-1": record(RUN, LifecycleState.SUCCEEDED)}
    if exposure_record is not None:
        records["exposure-1"] = exposure_record
    recorded: list[RemoteDeploymentReceipt] = []
    with pytest.raises(RuntimeError) as raised:
        coordinator(Runtime(), Store(records), recorded, FailingExposure(error)).deploy(
            request(True)
        )

    assert raised.value is error and recorded == []


def test_missing_terminal_commit_fails_closed() -> None:
    incomplete = DurableOperationRecord(RUN, REVISION, LifecycleState.SUCCEEDED)
    with pytest.raises(RemoteDeploymentIncompleteError):
        coordinator(Runtime(), Store({"run-1": incomplete})).deploy(request())
