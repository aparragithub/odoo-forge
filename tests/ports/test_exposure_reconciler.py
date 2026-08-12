from __future__ import annotations

import inspect
from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.backend.status import InstanceRef
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.deployment_spec import (
    DeploymentSpec,
    ExposureIntent,
    OdooRuntimeIntent,
    RequirementPolicy,
    RouteProtocol,
)
from odoo_forge.durable_operations import DurableOperationIdentity, RedactedEvidence
from odoo_forge.exposure.types import (
    ExposureCheckStatus,
    ExposureOutcome,
    ExposureRequest,
    ExposureResult,
    TlsStatus,
)
from odoo_forge.instance_registry.types import InstanceId, InstancePointer
from odoo_forge.ports.exposure_reconciler import ExposureReconciler
from odoo_forge.resource_ownership import (
    OwnershipReceipt,
    OwnershipRecord,
    ResourceOwnership,
    ResourceRef,
)
from odoo_forge.tenancy import ProjectScope, TenantId

SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
OPERATION = DurableOperationIdentity(operation_id="exposure-1", request_digest="digest-1")
INSTANCE = InstanceRef(
    project="project-1",
    instance="odoo",
    network="odoo-network",
    postgres_container="odoo-db",
    odoo_container="odoo-app",
)
RESOURCE = ResourceRef(
    identifier="runtime-1", resource_kind="runtime", ownership=ResourceOwnership.CREATED
)
OWNERSHIP = OwnershipRecord(
    ref=RESOURCE,
    receipt=OwnershipReceipt(operation=OPERATION, owned_resource_ids=("runtime-1",)),
)


def _deployment(*, tls: RequirementPolicy = RequirementPolicy.DISABLED) -> DeploymentSpec:
    protocol = RouteProtocol.HTTPS if tls is RequirementPolicy.REQUIRED else RouteProtocol.HTTP
    return DeploymentSpec(
        pointer=InstancePointer(scope=SCOPE, instance_id=InstanceId(value="odoo")),
        resource=RESOURCE,
        runtime=OdooRuntimeIntent(odoo_version="18.0"),
        exposure=ExposureIntent(
            hostname="odoo.example.test",
            protocol=protocol,
            dns=RequirementPolicy.REQUIRED,
            tls=tls,
        ),
    )


def _request() -> ExposureRequest:
    return ExposureRequest(
        instance=INSTANCE,
        deployment=_deployment(tls=RequirementPolicy.REQUIRED),
        scope=SCOPE,
        operation=OPERATION,
        ownership=(OWNERSHIP,),
        credential_handles=(CredentialHandle("ssh-handle-1"),),
    )


class _ConformingExposureReconciler:
    def reconcile(self, request: ExposureRequest) -> ExposureResult:
        return ExposureResult(
            operation=request.operation,
            outcome=ExposureOutcome.READY,
            routing_status=ExposureCheckStatus.VERIFIED,
            dns_status=ExposureCheckStatus.VERIFIED,
            ready=True,
            tls_status=TlsStatus.DEFERRED,
            tls_ready=False,
            ownership=request.ownership,
            evidence=(
                RedactedEvidence(
                    event="exposure-verified",
                    summary="HTTP routing and DNS verified",
                    references=("runtime-1",),
                ),
            ),
        )


def test_exposure_request_preserves_scope_identity_ownership_and_opaque_credentials() -> None:
    request = _request()

    assert request.scope is SCOPE
    assert request.operation is OPERATION
    assert request.ownership == (OWNERSHIP,)
    assert request.credential_handles == ("ssh-handle-1",)
    assert request.deployment.exposure is not None
    assert request.deployment.exposure.tls is RequirementPolicy.REQUIRED
    with pytest.raises(ValidationError):
        cast(Any, request).scope = ProjectScope(
            tenant=TenantId(value="other"), project_id="other-project"
        )


def test_exposure_request_rejects_instance_outside_scope() -> None:
    values = _request().model_dump()
    values["instance"] = INSTANCE.model_copy(update={"project": "project-2"})

    with pytest.raises(ValidationError, match="instance scope"):
        ExposureRequest(**values)


def test_exposure_request_rejects_deployment_outside_scope() -> None:
    other_scope = ProjectScope(tenant=TenantId(value="tenant-2"), project_id="project-2")
    deployment = _deployment().model_copy(
        update={"pointer": InstancePointer(scope=other_scope, instance_id=InstanceId(value="odoo"))}
    )

    values = _request().model_dump()
    values["deployment"] = deployment

    with pytest.raises(ValidationError, match="deployment scope"):
        ExposureRequest(**values)


def test_exposure_request_rejects_ownership_from_another_operation() -> None:
    other_operation = DurableOperationIdentity(operation_id="exposure-2", request_digest="digest-2")
    assert OWNERSHIP.receipt is not None
    ownership = OWNERSHIP.model_copy(
        update={"receipt": OWNERSHIP.receipt.model_copy(update={"operation": other_operation})},
    )
    values = _request().model_dump()
    values["ownership"] = (ownership,)

    with pytest.raises(ValidationError, match="ownership operation"):
        ExposureRequest(**values)


def test_exposure_result_rejects_ownership_from_another_operation() -> None:
    other_operation = DurableOperationIdentity(operation_id="exposure-2", request_digest="digest-2")
    assert OWNERSHIP.receipt is not None
    ownership = OWNERSHIP.model_copy(
        update={"receipt": OWNERSHIP.receipt.model_copy(update={"operation": other_operation})},
    )

    with pytest.raises(ValidationError, match="ownership operation"):
        ExposureResult(
            operation=OPERATION,
            outcome=ExposureOutcome.FAILED,
            ownership=(ownership,),
        )


def test_exposure_result_reports_http_readiness_without_claiming_tls_readiness() -> None:
    result = _ConformingExposureReconciler().reconcile(_request())

    assert result.outcome is ExposureOutcome.READY
    assert result.routing_status is ExposureCheckStatus.VERIFIED
    assert result.dns_status is ExposureCheckStatus.VERIFIED
    assert result.ready is True
    assert result.tls_status is TlsStatus.DEFERRED
    assert result.tls_ready is False
    assert result.evidence[0].references == ("runtime-1",)


def test_tls_readiness_cannot_be_claimed_by_the_contract() -> None:
    with pytest.raises(ValidationError):
        ExposureResult(
            operation=OPERATION,
            outcome=ExposureOutcome.READY,
            routing_status=ExposureCheckStatus.VERIFIED,
            dns_status=ExposureCheckStatus.VERIFIED,
            ready=True,
            tls_status=TlsStatus.DEFERRED,
            tls_ready=True,
        )


def test_exposure_result_rejects_unredacted_evidence() -> None:
    with pytest.raises(ValidationError):
        ExposureResult(
            operation=OPERATION,
            outcome=ExposureOutcome.FAILED,
            evidence=(RedactedEvidence(event="failure", summary="password=plaintext"),),
        )


def test_exposure_reconciler_is_a_runtime_checkable_single_reconcile_port() -> None:
    reconciler = _ConformingExposureReconciler()

    assert isinstance(reconciler, ExposureReconciler)
    assert list(inspect.signature(ExposureReconciler.reconcile).parameters) == [
        "self",
        "request",
    ]


def test_non_conforming_exposure_reconciler_is_rejected() -> None:
    class _MissingReconcile:
        pass

    assert not isinstance(_MissingReconcile(), ExposureReconciler)
