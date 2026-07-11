from odoo_forge.database.readiness import GateReadinessEvidence, evaluate_gate_readiness


def test_complete_readiness_evidence_is_ready_without_portfolio_mutation() -> None:
    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            approved_proposal_id="proposal-42",
            approved_specification_id="spec-42",
            approved_design_id="design-42",
            verification_receipt_id="verification-42",
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
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == (
        "approved_specification_id",
        "verification_receipt_id",
    )
