from typing import cast

import pytest

import odoo_forge.database.readiness as readiness_module
from odoo_forge.database import CreationReceipt, DatabaseCreation, DatabaseRef, OperationIdentity
from odoo_forge.database.readiness import (
    DeliverySliceEvidence,
    GateReadinessEvidence,
    RuntimeOwnershipEvidence,
    evaluate_gate_readiness,
)
from odoo_forge.database.types import ResourceOwnership

_CURRENT_EVIDENCE = frozenset({"#4406", "#4396", "#4398", "#4469", "#4463", "#4500"})


def _complete_gate_evidence(
    *,
    runtime_ownership_evidence: RuntimeOwnershipEvidence | None,
    approved_decision_id: str | None = "#4500",
    current_evidence_ids: frozenset[str] = _CURRENT_EVIDENCE,
    delivery_line_count: int | None = None,
    delivery_strategy: str | None = None,
    chain_strategy: str | None = None,
    delivery_slices: tuple[DeliverySliceEvidence, ...] = (),
) -> GateReadinessEvidence:
    return GateReadinessEvidence(
        wf_data_copy_closure_id="#4406",
        wf_data_copy_acceptance_id="#4396",
        wf_data_copy_verification_id="#4398",
        control_plane_archive_id="#4469",
        control_plane_verification_id="#4463",
        approved_decision_id=approved_decision_id,
        current_evidence_ids=current_evidence_ids,
        runtime_ownership_evidence=runtime_ownership_evidence,
        delivery_line_count=delivery_line_count,
        delivery_strategy=delivery_strategy,
        chain_strategy=chain_strategy,
        delivery_slices=delivery_slices,
    )


def test_complete_readiness_evidence_requires_a_runtime_attestation() -> None:
    result = evaluate_gate_readiness(
        _complete_gate_evidence(runtime_ownership_evidence=cast(RuntimeOwnershipEvidence, object()))
    )

    assert result.is_ready is False
    assert result.missing_identifiers == ("runtime_ownership_evidence",)


def test_apply_gate_satisfied_with_current_bounded_slice() -> None:
    result = evaluate_gate_readiness(
        _complete_gate_evidence(
            runtime_ownership_evidence=object.__new__(RuntimeOwnershipEvidence),
            delivery_line_count=180,
            delivery_slices=(
                DeliverySliceEvidence(
                    slice_id="slice-1",
                    parent_slice_id=None,
                    line_count=180,
                    verification_command="uv run pytest tests/database/test_readiness.py -q",
                    rollback_boundary="revert readiness contract files",
                ),
            ),
        )
    )

    assert result.is_ready is True
    assert result.missing_identifiers == ()


def test_apply_gate_blocked_when_dependency_evidence_is_missing() -> None:
    result = evaluate_gate_readiness(
        _complete_gate_evidence(
            runtime_ownership_evidence=object.__new__(RuntimeOwnershipEvidence),
            approved_decision_id=None,
            current_evidence_ids=frozenset(_CURRENT_EVIDENCE - {"#4500"}),
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == ("approved_decision_id", "approved_decision_id_current")


def test_oversized_delivery_requires_bounded_auto_chained_slices() -> None:
    unsplit = evaluate_gate_readiness(
        _complete_gate_evidence(
            runtime_ownership_evidence=object.__new__(RuntimeOwnershipEvidence),
            delivery_line_count=801,
            delivery_strategy="auto-chain",
            chain_strategy="stacked-to-main",
            delivery_slices=(
                DeliverySliceEvidence(
                    slice_id="slice-1",
                    parent_slice_id=None,
                    line_count=801,
                    verification_command="uv run pytest tests/database/test_readiness.py -q",
                    rollback_boundary="revert readiness contract files",
                ),
            ),
        )
    )
    split = evaluate_gate_readiness(
        _complete_gate_evidence(
            runtime_ownership_evidence=object.__new__(RuntimeOwnershipEvidence),
            delivery_line_count=801,
            delivery_strategy="auto-chain",
            chain_strategy="stacked-to-main",
            delivery_slices=(
                DeliverySliceEvidence(
                    slice_id="slice-1",
                    parent_slice_id=None,
                    line_count=400,
                    verification_command="uv run pytest tests/database/test_readiness.py -q",
                    rollback_boundary="revert readiness contract files",
                ),
                DeliverySliceEvidence(
                    slice_id="slice-2",
                    parent_slice_id="slice-1",
                    line_count=400,
                    verification_command="uv run pytest tests/database/test_readiness.py -q",
                    rollback_boundary="revert readiness contract files",
                ),
                DeliverySliceEvidence(
                    slice_id="slice-3",
                    parent_slice_id="slice-2",
                    line_count=1,
                    verification_command="uv run pytest tests/database/test_readiness.py -q",
                    rollback_boundary="revert readiness contract files",
                ),
            ),
        )
    )

    assert unsplit.is_ready is False
    assert unsplit.missing_identifiers == ("oversized_delivery",)
    assert split.is_ready is True


def test_oversized_delivery_requires_linkage_and_concrete_boundaries() -> None:
    result = evaluate_gate_readiness(
        _complete_gate_evidence(
            runtime_ownership_evidence=object.__new__(RuntimeOwnershipEvidence),
            delivery_line_count=801,
            delivery_strategy="manual",
            chain_strategy="none",
            delivery_slices=(
                DeliverySliceEvidence(
                    slice_id="slice-1",
                    parent_slice_id="unexpected-parent",
                    line_count=400,
                    verification_command="",
                    rollback_boundary="",
                ),
                DeliverySliceEvidence(
                    slice_id="slice-2",
                    parent_slice_id="not-slice-1",
                    line_count=401,
                    verification_command="",
                    rollback_boundary="",
                ),
            ),
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == (
        "oversized_delivery",
        "slice_verification_boundary",
        "slice_rollback_boundary",
        "autonomous_auto_chain",
        "auto_chain_linkage",
    )


def test_incomplete_readiness_evidence_identifies_every_missing_requirement() -> None:
    result = evaluate_gate_readiness(
        GateReadinessEvidence(
            wf_data_copy_closure_id=None,
            wf_data_copy_acceptance_id=None,
            wf_data_copy_verification_id=None,
            control_plane_archive_id=None,
            control_plane_verification_id=None,
            approved_decision_id=None,
            current_evidence_ids=frozenset(),
            runtime_ownership_evidence=cast(RuntimeOwnershipEvidence, object()),
        )
    )

    assert result.is_ready is False
    assert result.missing_identifiers == (
        "wf_data_copy_closure_id",
        "wf_data_copy_acceptance_id",
        "wf_data_copy_verification_id",
        "control_plane_archive_id",
        "control_plane_verification_id",
        "approved_decision_id",
        "wf_data_copy_closure_id_current",
        "wf_data_copy_acceptance_id_current",
        "wf_data_copy_verification_id_current",
        "control_plane_archive_id_current",
        "control_plane_verification_id_current",
        "approved_decision_id_current",
        "runtime_ownership_evidence",
    )


@pytest.mark.parametrize("value", [None, False, True, object()])
def test_plain_or_missing_runtime_values_cannot_pass_readiness(value: object) -> None:
    evidence = _complete_gate_evidence(
        runtime_ownership_evidence=cast(RuntimeOwnershipEvidence | None, value),
    )

    result = evaluate_gate_readiness(evidence)

    assert result.is_ready is False
    assert result.missing_identifiers == ("runtime_ownership_evidence",)


def test_direct_runtime_attestation_construction_is_refused() -> None:
    with pytest.raises((TypeError, ValueError)):
        RuntimeOwnershipEvidence()

    assert not hasattr(RuntimeOwnershipEvidence, "from_verified_creation")
    assert not hasattr(readiness_module, "_mint_runtime_ownership_evidence")


def test_manually_built_database_creation_cannot_pass_readiness() -> None:
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token-42"),
            owned_resource_ids=("database-42",),
        ),
    )

    result = evaluate_gate_readiness(
        _complete_gate_evidence(runtime_ownership_evidence=cast(RuntimeOwnershipEvidence, creation))
    )

    assert result.is_ready is False
    assert result.missing_identifiers == ("runtime_ownership_evidence",)
