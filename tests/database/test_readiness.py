import pytest

from odoo_forge.database.readiness import GateReadinessEvidence, evaluate_gate_readiness


def test_complete_readiness_evidence_is_ready_without_portfolio_mutation() -> None:
    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id="spec-42",
            approved_design_id="design-42",
            verification_receipt_id="verification-42",
            real_docker_verified=True,
            ownership_safety_verified=True,
        )
    )

    assert result.is_ready is True
    assert result.missing_identifiers == ()


def test_incomplete_readiness_evidence_identifies_every_missing_requirement() -> None:
    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id=None,
            approved_design_id="design-42",
            verification_receipt_id=None,
            real_docker_verified=True,
            ownership_safety_verified=True,
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == (
        "approved_specification_id",
        "verification_receipt_id",
    )


@pytest.mark.parametrize("value", [None, False])
@pytest.mark.parametrize("missing_flag", ["real_docker_verified", "ownership_safety_verified"])
def test_missing_or_simulated_runtime_evidence_blocks_readiness(
    missing_flag: str, value: bool | None
) -> None:
    if missing_flag == "real_docker_verified":
        evidence = GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id="spec-42",
            approved_design_id="design-42",
            verification_receipt_id="verification-42",
            real_docker_verified=value,
            ownership_safety_verified=True,
        )
    else:
        evidence = GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id="spec-42",
            approved_design_id="design-42",
            verification_receipt_id="verification-42",
            real_docker_verified=True,
            ownership_safety_verified=value,
        )

    result = evaluate_gate_readiness(evidence)

    assert result.is_ready is False
    assert result.missing_identifiers == (missing_flag,)
