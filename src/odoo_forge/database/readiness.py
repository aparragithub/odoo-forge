"""Pure readiness evaluation for database provider gate evidence."""

from __future__ import annotations

from dataclasses import dataclass

_RUNTIME_OWNERSHIP_MARKER = object()


class RuntimeOwnershipEvidence:
    """Opaque proof minted only after adapter-specific runtime verification."""

    __slots__ = ("_marker",)

    def __init__(self, *, marker: object) -> None:
        if marker is not _RUNTIME_OWNERSHIP_MARKER:
            raise ValueError("runtime ownership evidence must be provider-derived")
        self._marker = marker

    @property
    def is_trusted(self) -> bool:
        return self._marker is _RUNTIME_OWNERSHIP_MARKER


def _mint_runtime_ownership_evidence() -> RuntimeOwnershipEvidence:
    """Create an attestation for an adapter that has completed live verification."""
    return RuntimeOwnershipEvidence(marker=_RUNTIME_OWNERSHIP_MARKER)


@dataclass(frozen=True)
class GateReadinessEvidence:
    approved_proposal_id: str | None
    approved_specification_id: str | None
    approved_design_id: str | None
    verification_receipt_id: str | None
    runtime_ownership_evidence: RuntimeOwnershipEvidence | None = None


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
    ) + (
        ()
        if isinstance(evidence.runtime_ownership_evidence, RuntimeOwnershipEvidence)
        and evidence.runtime_ownership_evidence.is_trusted
        else ("runtime_ownership_evidence",)
    )
    return GateReadiness(
        is_ready=not missing_identifiers,
        missing_identifiers=missing_identifiers,
    )


__all__ = [
    "GateReadiness",
    "GateReadinessEvidence",
    "RuntimeOwnershipEvidence",
    "evaluate_gate_readiness",
]
