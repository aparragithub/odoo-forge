from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.resource_ownership import (
    CreationReceipt,
    OperationIdentity,
    OwnershipAttestation,
    OwnershipReceipt,
    OwnershipRecord,
    ResourceOwnership,
    ResourceRef,
    TenantAttribution,
)


def _ref(ownership: ResourceOwnership = ResourceOwnership.CREATED) -> ResourceRef:
    return ResourceRef(identifier="database-42", resource_kind="database", ownership=ownership)


def _durable_identity() -> DurableOperationIdentity:
    return DurableOperationIdentity(operation_id="provision-42", request_digest="digest-42")


def _receipt() -> OwnershipReceipt:
    return OwnershipReceipt(
        operation=_durable_identity(),
        owned_resource_ids=("database-42",),
        live_proof_expected=True,
    )


def test_ownership_state_model_has_exactly_three_states() -> None:
    assert {ownership.value for ownership in ResourceOwnership} == {
        "created",
        "adopted",
        "external",
    }


def test_resource_ref_is_frozen_and_opaque_across_resource_kinds() -> None:
    database_ref = _ref()
    container_ref = ResourceRef(
        identifier="container-7", resource_kind="container", ownership=ResourceOwnership.ADOPTED
    )

    assert database_ref.resource_kind == "database"
    assert container_ref.resource_kind == "container"
    assert container_ref.ownership is ResourceOwnership.ADOPTED
    with pytest.raises(ValidationError):
        cast(Any, database_ref).ownership = ResourceOwnership.EXTERNAL


def test_ownership_receipt_carries_operation_proof_owned_ids_and_live_proof_expectation() -> None:
    receipt = _receipt()

    assert receipt.operation == _durable_identity()
    assert receipt.owned_resource_ids == ("database-42",)
    assert receipt.live_proof_expected is True


def test_ownership_receipt_reuses_durable_operation_identity() -> None:
    """Spec scenario: ownership receipt reuses durable operation identity.

    GIVEN an adapter issues an ownership receipt for a durably tracked operation
    WHEN the receipt's operation proof is constructed
    THEN it is derived from the CAP-DURABLE-OPERATIONS operation identity.
    """
    identity = DurableOperationIdentity(operation_id="provision-77", request_digest="digest-77")

    receipt = OwnershipReceipt(operation=identity, owned_resource_ids=("database-77",))

    assert receipt.operation is identity
    assert receipt.operation.operation_id == "provision-77"
    assert receipt.operation.matches_request_digest("digest-77")


def test_ownership_receipt_rejects_a_parallel_operation_identity_model() -> None:
    """Spec scenario: a parallel operation-identity model is rejected as a duplicate.

    GIVEN a change defines a new operation-identity model for ownership evidence
    WHEN it is reviewed against this capability
    THEN the change is rejected as a duplicate of CAP-DURABLE-OPERATIONS.
    """
    with pytest.raises(ValidationError):
        # Deliberately passing the legacy, non-composed identity model to prove the
        # receipt rejects it at runtime — this is the exact case the type checker
        # already forbids statically, so the mismatch is intentional here.
        OwnershipReceipt(
            operation=cast(Any, OperationIdentity(value="legacy-token")),
            owned_resource_ids=("database-77",),
        )


def test_ownership_record_composes_optional_tenant_attribution_and_receipt() -> None:
    unattributed = OwnershipRecord(ref=_ref(ResourceOwnership.EXTERNAL))
    attributed = OwnershipRecord(
        ref=_ref(ResourceOwnership.ADOPTED),
        attribution=TenantAttribution(tenant_id="tenant-1"),
        receipt=_receipt(),
    )

    assert unattributed.attribution is None
    assert unattributed.receipt is None
    assert attributed.attribution == TenantAttribution(tenant_id="tenant-1")
    assert attributed.receipt == _receipt()


def test_tenant_attribution_composes_without_mandatory_linkage() -> None:
    external = TenantAttribution()

    assert external.tenant_id is None


def test_ownership_attestation_reports_attested_and_live_proof_verification() -> None:
    attestation = OwnershipAttestation(resource=_ref(), attested=True, live_proof_verified=True)

    assert attestation.resource == _ref()
    assert attestation.attested is True
    assert attestation.live_proof_verified is True


def test_ownership_values_reject_new_ownership_states() -> None:
    with pytest.raises(ValueError):
        ResourceOwnership("reserved")


def test_relocated_operation_identity_and_creation_receipt_preserve_prior_shape() -> None:
    receipt = CreationReceipt(
        operation=OperationIdentity(value="provision-99"), owned_resource_ids=("database-99",)
    )

    assert receipt.operation == OperationIdentity(value="provision-99")
    assert receipt.owned_resource_ids == ("database-99",)
