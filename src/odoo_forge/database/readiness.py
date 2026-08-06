"""Pure readiness evaluation for database provider gate evidence."""

from __future__ import annotations

from dataclasses import dataclass, field

_MAX_REVIEW_LINES = 400

_REQUIRED_ARCHIVED_EVIDENCE = (
    ("wf_data_copy_closure_id", "#4406"),
    ("wf_data_copy_acceptance_id", "#4396"),
    ("wf_data_copy_verification_id", "#4398"),
    ("control_plane_archive_id", "#4469"),
    ("control_plane_verification_id", "#4463"),
    ("approved_decision_id", "#4500"),
)


class RuntimeOwnershipEvidence:
    """Opaque proof minted only after adapter-specific runtime verification."""

    __slots__ = ()

    def __new__(cls) -> RuntimeOwnershipEvidence:
        raise TypeError("runtime ownership evidence must be provider-derived")


@dataclass(frozen=True)
class DeliverySliceEvidence:
    """Concrete evidence for one autonomous delivery slice."""

    slice_id: str
    parent_slice_id: str | None
    line_count: int
    verification_command: str
    rollback_boundary: str


@dataclass(frozen=True)
class GateReadinessEvidence:
    wf_data_copy_closure_id: str | None = None
    wf_data_copy_acceptance_id: str | None = None
    wf_data_copy_verification_id: str | None = None
    control_plane_archive_id: str | None = None
    control_plane_verification_id: str | None = None
    approved_decision_id: str | None = None
    current_evidence_ids: frozenset[str] = field(default_factory=frozenset)
    runtime_ownership_evidence: RuntimeOwnershipEvidence | None = None
    delivery_line_count: int | None = None
    delivery_strategy: str | None = None
    chain_strategy: str | None = None
    delivery_slices: tuple[DeliverySliceEvidence, ...] = ()


@dataclass(frozen=True)
class GateReadiness:
    is_ready: bool
    missing_identifiers: tuple[str, ...]


def evaluate_gate_readiness(evidence: GateReadinessEvidence) -> GateReadiness:
    missing: list[str] = []
    current = evidence.current_evidence_ids
    for field_name, expected_id in _REQUIRED_ARCHIVED_EVIDENCE:
        if getattr(evidence, field_name) != expected_id:
            missing.append(field_name)
    for field_name, expected_id in _REQUIRED_ARCHIVED_EVIDENCE:
        if expected_id not in current:
            missing.append(f"{field_name}_current")

    if not isinstance(evidence.runtime_ownership_evidence, RuntimeOwnershipEvidence):
        missing.append("runtime_ownership_evidence")

    if evidence.delivery_line_count is not None:
        slices = evidence.delivery_slices
        valid_counts = (
            bool(slices)
            and sum(slice_evidence.line_count for slice_evidence in slices)
            == evidence.delivery_line_count
            and all(0 < slice_evidence.line_count <= _MAX_REVIEW_LINES for slice_evidence in slices)
        )
        valid_boundaries = all(
            slice_evidence.slice_id
            and slice_evidence.verification_command
            and slice_evidence.rollback_boundary
            for slice_evidence in slices
        )
        if not valid_counts:
            missing.append(
                "oversized_delivery"
                if evidence.delivery_line_count > _MAX_REVIEW_LINES
                else "delivery_slices"
            )
        if not valid_boundaries:
            missing.extend(("slice_verification_boundary", "slice_rollback_boundary"))

        if evidence.delivery_line_count > _MAX_REVIEW_LINES:
            if (
                evidence.delivery_strategy != "auto-chain"
                or evidence.chain_strategy != "stacked-to-main"
            ):
                missing.append("autonomous_auto_chain")
            ids = tuple(slice_evidence.slice_id for slice_evidence in slices)
            linked = (
                bool(ids)
                and len(set(ids)) == len(ids)
                and slices[0].parent_slice_id is None
                and all(
                    slice_evidence.parent_slice_id == ids[index - 1]
                    for index, slice_evidence in enumerate(slices[1:], start=1)
                )
            )
            if not linked:
                missing.append("auto_chain_linkage")

    return GateReadiness(
        is_ready=not missing,
        missing_identifiers=tuple(missing),
    )


__all__ = [
    "DeliverySliceEvidence",
    "GateReadiness",
    "GateReadinessEvidence",
    "RuntimeOwnershipEvidence",
    "evaluate_gate_readiness",
]
