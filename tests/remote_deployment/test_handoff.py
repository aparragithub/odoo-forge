import pytest

from odoo_forge.backend.plan import BackendPlan, ContainerSpec, NetworkSpec
from odoo_forge.backend.status import InstanceRef
from odoo_forge.deployment_spec.types import (
    DeploymentSpec,
    ExposureIntent,
    OdooRuntimeIntent,
    RequirementPolicy,
    RouteProtocol,
)
from odoo_forge.durable_operations.service import build_terminal_commit, save_checkpoint
from odoo_forge.durable_operations.types import (
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
)
from odoo_forge.exposure.types import ExposureCheckStatus, ExposureOutcome, ExposureResult
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.ports.durable_operation_store import DurableOperationRecord
from odoo_forge.remote_deployment import (
    RemoteDeploymentCoordinator,
    RemoteDeploymentIncompleteError,
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


def owner(operation: DurableOperationIdentity, identifier: str) -> OwnershipRecord:
    ref = ResourceRef(
        identifier=identifier, resource_kind="container", ownership=ResourceOwnership.CREATED
    )
    return OwnershipRecord(
        ref=ref, receipt=OwnershipReceipt(operation=operation, owned_resource_ids=(identifier,))
    )


def deployment(exposed: bool = False) -> DeploymentSpec:
    return DeploymentSpec(
        pointer=POINTER,
        resource=ResourceRef(
            identifier="odoo-forge-project-1-one",
            resource_kind="network",
            ownership=ResourceOwnership.CREATED,
        ),
        runtime=OdooRuntimeIntent(odoo_version="18.0"),
        exposure=ExposureIntent(
            hostname="one.example",
            protocol=RouteProtocol.HTTP,
            dns=RequirementPolicy.REQUIRED,
            tls=RequirementPolicy.DISABLED,
        )
        if exposed
        else None,
    )


def plan() -> BackendPlan:
    network = NetworkSpec(name="odoo-forge-project-1-one", labels={"managed": "true"})
    db = ContainerSpec(
        name="db-one", image="postgres:16", role="postgres", network=network.name, env={}, labels={}
    )
    odoo = ContainerSpec(
        name="odoo-one",
        image="odoo-forge-odoo:18.0",
        role="odoo",
        network=network.name,
        env={},
        labels={},
    )
    return BackendPlan(network=network, volumes=[], postgres=db, odoo=odoo)


def request(exposed=False, exposure_operation=EXPOSURE):
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
    checkpoint = save_checkpoint(OperationRevision(value=0), "ready", evidence)
    terminal = build_terminal_commit(OperationRevision(value=1), outcome, (evidence,), ())
    return DurableOperationRecord(
        identity=operation,
        revision=OperationRevision(value=2),
        lifecycle=outcome,
        checkpoint=checkpoint,
        terminal_commit=terminal,
        recovery_evidence=(evidence,),
    )


class Store(dict):
    def create_or_load(self, operation):
        return self[operation.operation_id]


class Runtime:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def run(self, value):
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
    def __init__(self, result):
        self.result, self.requests = result, []

    def reconcile(self, request):
        self.requests.append(request)
        return self.result


def coordinator(runtime, store, recorded=None, exposure=None):
    sink = recorded if recorded is not None else []
    return RemoteDeploymentCoordinator(
        runtime_provider=runtime,
        operation_store=store,
        recorder=sink.append,
        exposure_provider=exposure,
    )


def test_success_receipt_preserves_target_label_and_runtime_ownership():
    runtime, store, recorded = (
        Runtime(),
        Store({"run-1": record(RUN, LifecycleState.SUCCEEDED)}),
        [],
    )
    receipt = coordinator(runtime, store, recorded).deploy(request())
    assert (receipt.provider, receipt.target, receipt.runtime_operation) == ("vps", TARGET, RUN)
    assert (
        receipt.runtime_ownership == (owner(RUN, "odoo-one"),) and receipt.exposure_ownership == ()
    )
    assert receipt.outcome is LifecycleState.SUCCEEDED and recorded == [receipt]


def test_exposure_uses_empty_input_and_operation_matched_ownership():
    route = owner(EXPOSURE, "route-one")
    result = ExposureResult(
        operation=EXPOSURE,
        outcome=ExposureOutcome.READY,
        routing_status=ExposureCheckStatus.VERIFIED,
        dns_status=ExposureCheckStatus.VERIFIED,
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


def test_in_progress_exposure_fails_closed_without_receipt():
    result = ExposureResult(operation=EXPOSURE, outcome=ExposureOutcome.IN_PROGRESS)
    pending = DurableOperationRecord(
        identity=EXPOSURE, revision=OperationRevision(value=1), lifecycle=LifecycleState.IN_PROGRESS
    )
    store = Store({"run-1": record(RUN, LifecycleState.SUCCEEDED), "exposure-1": pending})
    recorded = []
    with pytest.raises(RemoteDeploymentIncompleteError):
        coordinator(Runtime(), store, recorded, Exposure(result)).deploy(request(True))
    assert recorded == []


def test_same_runtime_and_exposure_operation_is_rejected_before_provider_call():
    with pytest.raises(RemoteDeploymentIncompleteError):
        coordinator((runtime := Runtime()), Store({})).deploy(request(True, exposure_operation=RUN))
    assert runtime.calls == []


def test_adapter_failure_records_failed_evidence_and_reraises_same_exception():
    error, failed = RuntimeError("adapter failure"), record(RUN, LifecycleState.FAILED)
    recorded = []
    with pytest.raises(RuntimeError) as raised:
        coordinator(Runtime(error), Store({"run-1": failed}), recorded).deploy(request())
    assert (
        raised.value is error
        and len(recorded) == 1
        and recorded[0].outcome is LifecycleState.FAILED
    )


def test_missing_terminal_commit_fails_closed():
    incomplete = DurableOperationRecord(
        identity=RUN, revision=OperationRevision(value=1), lifecycle=LifecycleState.SUCCEEDED
    )
    with pytest.raises(RemoteDeploymentIncompleteError):
        coordinator(Runtime(), Store({"run-1": incomplete})).deploy(request())
