import pytest
from pydantic import ValidationError

from odoo_forge.credentials import (
    CredentialHandle,
    CredentialInjectionDescriptor,
    TargetContext,
)
from odoo_forge.credentials.errors import (
    CredentialError,
    CredentialTargetRejectedError,
    CredentialUnavailableError,
)
from odoo_forge.credentials.materialization import materialize_for_target


@pytest.mark.parametrize(
    ("error_type", "expected_detail"),
    [
        (CredentialUnavailableError, "credential material is unavailable"),
        (CredentialTargetRejectedError, "credential target does not accept an opaque reference"),
    ],
)
def test_credential_errors_expose_only_redacted_public_detail(
    error_type: type[CredentialError], expected_detail: str
) -> None:
    secret = "super-secret-value"

    error = error_type(secret)

    assert str(error) == expected_detail
    assert error.detail == expected_detail
    assert secret not in str(error)
    assert secret not in error.detail


def test_injection_descriptor_contains_only_opaque_handoff_data() -> None:
    descriptor = CredentialInjectionDescriptor(
        handle=CredentialHandle("credential-42"),
        target_kind="database",
        store_ref="approved-store://credential-42",
        redaction_label="credential-42",
    )

    assert descriptor.model_dump() == {
        "handle": "credential-42",
        "target_kind": "database",
        "store_ref": "approved-store://credential-42",
        "redaction_label": "credential-42",
    }
    assert TargetContext(kind="database", target_id="database-42").model_dump() == {
        "kind": "database",
        "target_id": "database-42",
    }


def test_injection_values_reject_plaintext_bearing_fields() -> None:
    with pytest.raises(ValidationError):
        CredentialInjectionDescriptor.model_validate(
            {
                "handle": CredentialHandle("credential-42"),
                "target_kind": "database",
                "store_ref": "approved-store://credential-42",
                "redaction_label": "credential-42",
                "secret": "super-secret-value",
            }
        )

    with pytest.raises(ValidationError):
        TargetContext.model_validate(
            {
                "kind": "database",
                "target_id": "database-42",
                "password": "super-secret-value",
            }
        )


@pytest.mark.parametrize(
    ("handle", "target_id"),
    [
        (CredentialHandle("database-42"), "database-42"),
        (CredentialHandle("database-99"), "database-99"),
    ],
)
def test_sops_materialization_returns_only_an_opaque_reference(
    handle: CredentialHandle, target_id: str
) -> None:
    descriptor = materialize_for_target(
        handle,
        TargetContext(kind="database", target_id=target_id),
    )

    assert descriptor == CredentialInjectionDescriptor(
        handle=handle,
        target_kind="database",
        store_ref=f"sops://{handle}",
        redaction_label="SOPS credential",
    )
    assert "super-secret-value" not in descriptor.model_dump_json()


def test_non_ref_capable_target_fails_closed_without_exposing_diagnostic() -> None:
    with pytest.raises(CredentialTargetRejectedError) as excinfo:
        materialize_for_target(
            CredentialHandle("backend-42"),
            TargetContext(kind="backend", target_id="backend-42"),
        )

    assert str(excinfo.value) == "credential target does not accept an opaque reference"


def test_source_target_is_sops_ref_capable_for_enterprise_credential_convention() -> None:
    from odoo_forge.credentials.conventions import (
        ENTERPRISE_SOURCE_CREDENTIAL_HANDLE,
        ENTERPRISE_SOURCE_TARGET,
    )

    descriptor = materialize_for_target(
        ENTERPRISE_SOURCE_CREDENTIAL_HANDLE,
        ENTERPRISE_SOURCE_TARGET,
    )

    assert descriptor.store_ref == "sops://enterprise/source-git"
    assert descriptor.target_kind == "source"


def test_sops_store_ref_locks_the_conventional_enterprise_source_key() -> None:
    from odoo_forge.credentials.conventions import ENTERPRISE_SOURCE_CREDENTIAL_HANDLE
    from odoo_forge.credentials.materialization import _sops_store_ref

    assert _sops_store_ref(ENTERPRISE_SOURCE_CREDENTIAL_HANDLE) == "sops://enterprise/source-git"
