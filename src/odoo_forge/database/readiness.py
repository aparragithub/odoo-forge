"""Pure readiness evaluation for database provider gate evidence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GateReadinessEvidence:
    approved_proposal_id: str | None
    approved_specification_id: str | None
    approved_design_id: str | None
    verification_receipt_id: str | None


@dataclass(frozen=True)
class GateReadiness:
    is_ready: bool
    missing_identifiers: tuple[str, ...]


def evaluate_gate_readiness(evidence: GateReadinessEvidence) -> GateReadiness:
    required_identifiers = (
        "approved_proposal_id",
        "approved_specification_id",
        "approved_design_id",
        "verification_receipt_id",
    )
    missing_identifiers = tuple(
        identifier for identifier in required_identifiers if getattr(evidence, identifier) is None
    )
    return GateReadiness(
        is_ready=not missing_identifiers,
        missing_identifiers=missing_identifiers,
    )


__all__ = ["GateReadiness", "GateReadinessEvidence", "evaluate_gate_readiness"]
