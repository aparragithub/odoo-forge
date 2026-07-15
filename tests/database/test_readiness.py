from typing import cast

import pytest

from odoo_forge.database import CreationReceipt, DatabaseCreation, DatabaseRef, OperationIdentity
from odoo_forge.database.readiness import (
    GateReadinessEvidence,
    RuntimeOwnershipEvidence,
    evaluate_gate_readiness,
)
from odoo_forge.database.types import ResourceOwnership


def test_complete_readiness_evidence_requires_a_runtime_attestation() -> None:
    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id="spec-42",
            approved_design_id="design-42",
            verification_receipt_id="verification-42",
            runtime_ownership_evidence=cast(RuntimeOwnershipEvidence, object()),
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == ("runtime_ownership_evidence",)


def test_incomplete_readiness_evidence_identifies_every_missing_requirement() -> None:
    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id=None,
            approved_design_id="design-42",
            verification_receipt_id=None,
            runtime_ownership_evidence=cast(RuntimeOwnershipEvidence, object()),
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == (
        "approved_specification_id",
        "verification_receipt_id",
        "runtime_ownership_evidence",
    )


@pytest.mark.parametrize("value", [None, False, True, object()])
def test_plain_or_missing_runtime_values_cannot_pass_readiness(value: object) -> None:
    evidence = GateReadinessEvidence(
        approved_proposal_id="proposal-42",
        approved_specification_id="spec-42",
        approved_design_id="design-42",
        verification_receipt_id="verification-42",
        runtime_ownership_evidence=cast(RuntimeOwnershipEvidence | None, value),
    )

    result = evaluate_gate_readiness(evidence)

    assert result.is_ready is False
    assert result.missing_identifiers == ("runtime_ownership_evidence",)


def test_direct_runtime_attestation_construction_is_refused() -> None:
    with pytest.raises((TypeError, ValueError)):
        RuntimeOwnershipEvidence()  # type: ignore[call-arg]

    assert not hasattr(RuntimeOwnershipEvidence, "from_verified_creation")


def test_manually_built_database_creation_cannot_pass_readiness() -> None:
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token-42"),
            owned_resource_ids=("database-42",),
        ),
    )

    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id="spec-42",
            approved_design_id="design-42",
            verification_receipt_id="verification-42",
            runtime_ownership_evidence=cast(RuntimeOwnershipEvidence, creation),
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == ("runtime_ownership_evidence",)
