from datetime import UTC, datetime
from typing import get_type_hints

import pytest
from pydantic import ValidationError, ValidationInfo

from odoo_forge.data_environments.errors import (
    DataEnvironmentError,
    EnvironmentDefinitionUnavailableError,
    RawDataGrantRefusedError,
    RecoveryPointUnavailableError,
)
from odoo_forge.data_environments.types import (
    DataEnvironmentDefinition,
    EnvironmentFailureCode,
    EnvironmentLifecycle,
    EnvironmentOperationOutcome,
    EnvironmentOutcomeCode,
    EnvironmentRelationship,
    RawDataGrant,
)
from odoo_forge.ports.data_environment_registry import DataEnvironmentRegistry
from odoo_forge.ports.raw_data_grant_authority import RawDataGrantAuthority
from odoo_forge.tenancy import ProjectScope, TenantId


def _definition() -> DataEnvironmentDefinition:
    return DataEnvironmentDefinition(
        environment_id="qa",
        owner="platform",
        scope=ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1"),
        lifecycle=EnvironmentLifecycle.ACTIVE,
        policy_ref="policy-qa",
        relationships=(
            EnvironmentRelationship(source_environment_id="production", target_environment_id="qa"),
        ),
    )


def _grant() -> RawDataGrant:
    return RawDataGrant(
        operation_id="refresh-42",
        environment_id="qa",
        grantor="operator-1",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        reason="approved fixture refresh",
        audit_reference="audit-42",
    )


class _Registry:
    def resolve(self, environment_id: str) -> DataEnvironmentDefinition:
        assert environment_id == "qa"
        return _definition()


class _GrantAuthority:
    def authorize(self, operation_id: str, environment_id: str) -> RawDataGrant | None:
        assert (operation_id, environment_id) == ("refresh-42", "qa")
        return _grant()


def test_registry_and_raw_grant_authority_are_separate_contracts() -> None:
    registry = _Registry()
    grants = _GrantAuthority()

    assert isinstance(registry, DataEnvironmentRegistry)
    assert isinstance(grants, RawDataGrantAuthority)
    assert not isinstance(registry, RawDataGrantAuthority)
    assert not isinstance(grants, DataEnvironmentRegistry)
    assert registry.resolve("qa") == _definition()
    assert grants.authorize("refresh-42", "qa") == _grant()


def test_outcomes_are_fail_closed() -> None:
    succeeded = EnvironmentOperationOutcome(code=EnvironmentOutcomeCode.SUCCEEDED)
    refused = EnvironmentOperationOutcome(
        code=EnvironmentOutcomeCode.REFUSED,
        failure_code=EnvironmentFailureCode.AUTHORITY_UNAVAILABLE,
        redacted_detail="canonical definition unavailable",
    )

    assert succeeded.succeeded
    assert not refused.succeeded
    assert isinstance(DataEnvironmentError(), Exception)

    with pytest.raises(ValidationError):
        EnvironmentOperationOutcome(
            code=EnvironmentOutcomeCode.SUCCEEDED,
            failure_code=EnvironmentFailureCode.AUTHORITY_UNAVAILABLE,
        )
    with pytest.raises(ValidationError):
        EnvironmentOperationOutcome(code=EnvironmentOutcomeCode.REFUSED)


def test_data_environment_errors_describe_their_domain_meaning() -> None:
    assert "data-environment" in (DataEnvironmentError.__doc__ or "")
    assert "definition" in (EnvironmentDefinitionUnavailableError.__doc__ or "")
    assert "raw-data" in (RawDataGrantRefusedError.__doc__ or "")
    assert "recovery point" in (RecoveryPointUnavailableError.__doc__ or "")


@pytest.mark.parametrize(
    "validator",
    [
        EnvironmentRelationship.require_safe_ids,
        DataEnvironmentDefinition.require_safe_references,
        RawDataGrant.require_safe_references,
    ],
)
def test_field_validators_annotate_pydantic_validation_info(validator: object) -> None:
    hints = get_type_hints(validator)

    assert hints["info"] is ValidationInfo


def test_raw_grant_requires_expiry_reason_and_audit_reference() -> None:
    grant = _grant()

    assert grant.operation_id == "refresh-42"
    assert grant.environment_id == "qa"
    assert grant.expires_at.tzinfo is not None

    with pytest.raises(ValidationError):
        RawDataGrant.model_validate(
            {
                "operation_id": "refresh-42",
                "environment_id": "qa",
                "grantor": "operator-1",
                "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
                "reason": "",
                "audit_reference": "audit-42",
            }
        )

    with pytest.raises(ValidationError):
        RawDataGrant.model_validate(
            {
                "operation_id": "refresh-42",
                "environment_id": "qa",
                "grantor": "operator-1",
                "expires_at": datetime(2030, 1, 1),
                "reason": "approved fixture refresh",
                "audit_reference": "audit-42",
            }
        )

    with pytest.raises(ValidationError):
        RawDataGrant.model_validate(
            {
                "operation_id": "refresh-42",
                "environment_id": "qa",
                "grantor": "operator-1",
                "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
                "reason": "credential_secret=secret-sentinel",
                "audit_reference": "audit-42",
            }
        )


def test_outcome_rejects_secret_pattern_in_redacted_detail() -> None:
    with pytest.raises(ValidationError):
        EnvironmentOperationOutcome.model_validate(
            {
                "code": EnvironmentOutcomeCode.FAILED,
                "failure_code": EnvironmentFailureCode.INVALID_DEFINITION,
                "redacted_detail": "credential_secret=secret-sentinel",
            }
        )


def test_relationship_rejects_equal_source_and_target_ids() -> None:
    with pytest.raises(ValidationError):
        EnvironmentRelationship.model_validate(
            {"source_environment_id": "qa", "target_environment_id": "qa"}
        )
