from collections.abc import Callable
from dataclasses import dataclass

from odoo_forge.backend.plan import BackendPlan
from odoo_forge.backend.status import InstanceRef
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.deployment_spec.types import DeploymentSpec
from odoo_forge.durable_operations.types import DurableOperationIdentity, LifecycleState
from odoo_forge.exposure.types import ExposureOutcome, ExposureRequest, ExposureResult
from odoo_forge.ports.durable_operation_store import DurableOperationRecord, DurableOperationStore
from odoo_forge.resource_ownership.types import OwnershipRecord


class RemoteDeploymentIncompleteError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteTargetFingerprint:
    host: str
    user: str
    port: int
    host_key: str


@dataclass(frozen=True)
class RemoteDeploymentRequest:
    deployment: DeploymentSpec
    plan: BackendPlan
    target: RemoteTargetFingerprint
    runtime_operation: DurableOperationIdentity
    exposure_operation: DurableOperationIdentity | None = None
    runtime_ownership: tuple[OwnershipRecord, ...] = ()
    exposure_credential_handles: tuple[CredentialHandle, ...] = ()


@dataclass(frozen=True)
class RemoteDeploymentReceipt:
    deployment: DeploymentSpec
    provider: str
    target: RemoteTargetFingerprint
    runtime_ref: InstanceRef | None
    runtime_operation: DurableOperationIdentity
    runtime_ownership: tuple[OwnershipRecord, ...]
    runtime_terminal_record: DurableOperationRecord
    exposure_operation: DurableOperationIdentity | None
    exposure_result: ExposureResult | None
    exposure_ownership: tuple[OwnershipRecord, ...]
    exposure_terminal_record: DurableOperationRecord | None
    outcome: LifecycleState


Recorder = Callable[[RemoteDeploymentReceipt], None]


def _valid_terminal(record: DurableOperationRecord, operation: DurableOperationIdentity) -> bool:
    commit = record.terminal_commit
    return (
        record.identity == operation
        and record.lifecycle in (LifecycleState.SUCCEEDED, LifecycleState.FAILED)
        and commit is not None
        and commit.outcome is record.lifecycle
        and not commit.residual_cleanup
        and bool(commit.evidence)
    )


class RemoteDeploymentCoordinator:
    def __init__(
        self,
        *,
        runtime_provider: object,
        operation_store: DurableOperationStore,
        recorder: Recorder,
        exposure_provider: object | None = None,
    ) -> None:
        self._runtime_provider = runtime_provider
        self._exposure_provider = exposure_provider
        self._operation_store = operation_store
        self._recorder = recorder

    def deploy(self, request: RemoteDeploymentRequest) -> RemoteDeploymentReceipt:
        if not all(
            record.receipt is None or record.receipt.operation == request.runtime_operation
            for record in request.runtime_ownership
        ):
            raise RemoteDeploymentIncompleteError("runtime ownership is inconsistent")
        if request.deployment.exposure is None and request.exposure_operation is not None:
            raise RemoteDeploymentIncompleteError("exposure operation has no exposure intent")
        if request.deployment.exposure and request.exposure_operation == request.runtime_operation:
            raise RemoteDeploymentIncompleteError("runtime and exposure operations must differ")
        try:
            runtime_ref = self._runtime_provider.run(request.plan)  # type: ignore[attr-defined]
        except Exception:
            self._record_validated_failure(request)
            raise
        if (
            runtime_ref.project != request.deployment.pointer.scope.project_id
            or runtime_ref.instance != request.deployment.pointer.instance_id.value
            or runtime_ref.network != request.deployment.resource.identifier
        ):
            raise RemoteDeploymentIncompleteError("runtime identity is inconsistent")
        runtime_record = self._operation_store.create_or_load(request.runtime_operation)
        if not _valid_terminal(runtime_record, request.runtime_operation):
            raise RemoteDeploymentIncompleteError("runtime evidence is incomplete")
        if runtime_record.lifecycle is not LifecycleState.SUCCEEDED:
            raise RemoteDeploymentIncompleteError("runtime operation did not succeed")
        exposure_result: ExposureResult | None = None
        exposure_record: DurableOperationRecord | None = None
        exposure_ownership: tuple[OwnershipRecord, ...] = ()
        if request.deployment.exposure is not None:
            if self._exposure_provider is None or request.exposure_operation is None:
                raise RemoteDeploymentIncompleteError("exposure reconciliation is not composed")
            exposure_request = ExposureRequest(
                instance=runtime_ref,
                deployment=request.deployment,
                scope=request.deployment.pointer.scope,
                operation=request.exposure_operation,
                ownership=(),
                credential_handles=request.exposure_credential_handles,
            )
            exposure_result = self._exposure_provider.reconcile(exposure_request)  # type: ignore[attr-defined]
            exposure_record = self._operation_store.create_or_load(request.exposure_operation)
            if (
                not _valid_terminal(exposure_record, request.exposure_operation)
                or exposure_record.lifecycle is not LifecycleState.SUCCEEDED
                or exposure_result.operation != request.exposure_operation
                or exposure_result.outcome is not ExposureOutcome.READY
                or not exposure_result.ready
            ):
                raise RemoteDeploymentIncompleteError("exposure evidence is incomplete")
            exposure_ownership = exposure_result.ownership
        receipt = RemoteDeploymentReceipt(
            deployment=request.deployment,
            provider="vps",
            target=request.target,
            runtime_ref=runtime_ref,
            runtime_operation=request.runtime_operation,
            runtime_ownership=request.runtime_ownership,
            runtime_terminal_record=runtime_record,
            exposure_operation=request.exposure_operation,
            exposure_result=exposure_result,
            exposure_ownership=exposure_ownership,
            exposure_terminal_record=exposure_record,
            outcome=LifecycleState.SUCCEEDED,
        )
        self._recorder(receipt)
        return receipt

    def _record_validated_failure(self, request: RemoteDeploymentRequest) -> None:
        try:
            record = self._operation_store.create_or_load(request.runtime_operation)
            if not _valid_terminal(record, request.runtime_operation):
                return
            if record.lifecycle is not LifecycleState.FAILED:
                return
            self._recorder(
                RemoteDeploymentReceipt(
                    deployment=request.deployment,
                    provider="vps",
                    target=request.target,
                    runtime_ref=None,
                    runtime_operation=request.runtime_operation,
                    runtime_ownership=request.runtime_ownership,
                    runtime_terminal_record=record,
                    exposure_operation=None,
                    exposure_result=None,
                    exposure_ownership=(),
                    exposure_terminal_record=None,
                    outcome=LifecycleState.FAILED,
                )
            )
        except Exception:
            return
