import pytest
from pydantic import ValidationError

from odoo_forge.database import CleanupReport, DatabaseSpec
from odoo_forge.database.errors import (
    ArtifactUnavailableError,
    CredentialUnavailableError,
    DatabaseConflictError,
    DatabaseOperationError,
    DatabaseProviderError,
    DatabaseReadinessError,
    IncompleteCleanupError,
    InvalidDatabaseRequestError,
    OwnershipRefusedError,
    ResourceUnavailableError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidDatabaseRequestError,
        CredentialUnavailableError,
        ArtifactUnavailableError,
        ResourceUnavailableError,
        DatabaseConflictError,
        DatabaseReadinessError,
        OwnershipRefusedError,
        DatabaseOperationError,
        IncompleteCleanupError,
    ],
)
def test_database_provider_failures_are_a_typed_family(
    error_type: type[DatabaseProviderError],
) -> None:
    error = error_type("provider diagnostic")

    assert isinstance(error, DatabaseProviderError)
    assert isinstance(error, Exception)
    assert error.detail != "provider diagnostic"


@pytest.mark.parametrize(
    "secret_detail",
    [
        "credential_secret=super-secret",
        "artifact_bytes=database-dump",
    ],
)
def test_database_provider_failures_redact_sensitive_diagnostics(secret_detail: str) -> None:
    error = IncompleteCleanupError(secret_detail)

    assert secret_detail not in error.detail
    assert secret_detail not in str(error)
    assert error.detail == "database cleanup incomplete"


@pytest.mark.parametrize(
    "residual_failure",
    [
        "credential_secret=super-secret",
        "artifact_bytes=database-dump",
        b"database dump",
        b"database-42",
    ],
)
def test_cleanup_report_rejects_sensitive_residual_content(residual_failure: str | bytes) -> None:
    with pytest.raises(ValidationError):
        CleanupReport.model_validate({"residual_failures": (residual_failure,)})


def test_cleanup_report_preserves_safe_opaque_residual_identifiers() -> None:
    report = CleanupReport(residual_failures=("database-42", "network-42"))

    assert report.residual_failures == ("database-42", "network-42")


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "analytics", "credential_secret": "secret-sentinel"},
        {"name": "analytics", "artifact_bytes": b"artifact-sentinel"},
    ],
)
def test_provider_value_validation_diagnostics_hide_rejected_sensitive_input(
    payload: dict[str, str | bytes],
) -> None:
    with pytest.raises(ValidationError) as error:
        DatabaseSpec.model_validate(payload)

    assert "secret-sentinel" not in str(error.value)
    assert "artifact-sentinel" not in str(error.value)


def test_cleanup_residual_validation_diagnostics_hide_rejected_sensitive_input() -> None:
    with pytest.raises(ValidationError) as error:
        CleanupReport.model_validate({"residual_failures": ("credential_secret=secret-sentinel",)})

    assert "secret-sentinel" not in str(error.value)
