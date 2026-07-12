from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.durable_operations import (
    CompensationScope,
    DurableOperationIdentity,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
    ReplayConflictError,
)


def test_operation_identity_is_immutable_and_compares_only_its_request_digest() -> None:
    identity = DurableOperationIdentity(
        operation_id="operation-42", request_digest="sha256-request-42"
    )

    assert identity.matches_request_digest("sha256-request-42")
    assert not identity.matches_request_digest("sha256-request-99")
    with pytest.raises(ValidationError):
        cast(Any, identity).request_digest = "sha256-request-99"


def test_operation_identity_rejects_extra_request_payloads() -> None:
    with pytest.raises(ValidationError):
        DurableOperationIdentity.model_validate(
            {
                "operation_id": "operation-42",
                "request_digest": "sha256-request-42",
                "request_bytes": b"protected request",
            }
        )


def test_operation_identity_requires_non_empty_identity_and_digest() -> None:
    with pytest.raises(ValidationError):
        DurableOperationIdentity(operation_id="", request_digest="sha256-request-42")
    with pytest.raises(ValidationError):
        DurableOperationIdentity(operation_id="operation-42", request_digest="")


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (LifecycleState.ACCEPTED, "accepted"),
        (LifecycleState.CLEANUP_REQUIRED, "cleanup_required"),
        (LifecycleState.CLOSED, "closed"),
    ],
)
def test_lifecycle_states_have_stable_serialized_values(
    state: LifecycleState, expected: str
) -> None:
    assert state.value == expected


def test_operation_revision_is_non_negative_and_immutable() -> None:
    revision = OperationRevision(value=3)

    assert revision.value == 3
    with pytest.raises(ValidationError):
        OperationRevision(value=-1)
    with pytest.raises(ValidationError):
        cast(Any, revision).value = 4


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "password=super-secret",
        "postgres://user:password@db.example",
        "artifact_bytes=raw-data",
    ],
)
def test_redacted_evidence_rejects_secrets_connection_material_and_data_bytes(
    unsafe_value: str,
) -> None:
    with pytest.raises(ValidationError):
        RedactedEvidence(event="checkpoint", summary=unsafe_value)


def test_redacted_evidence_serializes_only_safe_audit_facts() -> None:
    evidence = RedactedEvidence(
        event="checkpoint-recorded",
        summary="provider receipt captured",
        references=("receipt-42",),
    )

    assert evidence.model_dump(mode="json") == {
        "event": "checkpoint-recorded",
        "summary": "provider receipt captured",
        "references": ["receipt-42"],
    }


def test_compensation_scope_targets_only_resources_owned_by_the_operation() -> None:
    scope = CompensationScope(
        operation_id="operation-42", owned_resource_ids=("database-42", "volume-42")
    )

    assert scope.owns("database-42")
    assert scope.owns("volume-42")
    assert not scope.owns("database-99")


def test_compensation_scope_rejects_unredacted_resource_identifiers() -> None:
    with pytest.raises(ValidationError):
        CompensationScope(
            operation_id="operation-42",
            owned_resource_ids=("postgres://user:password@db.example",),
        )


def test_replay_conflict_error_exposes_only_operation_and_digest_values() -> None:
    error = ReplayConflictError(
        operation_id="operation-42",
        recorded_request_digest="sha256-request-42",
        submitted_request_digest="sha256-request-99",
    )

    assert "operation-42" in str(error)
    assert "sha256-request-42" in str(error)
    assert "sha256-request-99" in str(error)
    assert "password" not in str(error).lower()
