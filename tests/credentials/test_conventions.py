from odoo_forge.credentials.conventions import (
    ENTERPRISE_SOURCE_CREDENTIAL_HANDLE,
    ENTERPRISE_SOURCE_TARGET,
)
from odoo_forge.credentials.types import CredentialHandle, TargetContext


def test_enterprise_source_credential_handle_is_the_conventional_name() -> None:
    assert CredentialHandle("enterprise/source-git") == ENTERPRISE_SOURCE_CREDENTIAL_HANDLE


def test_enterprise_source_target_is_a_source_kind_target_for_enterprise() -> None:
    assert TargetContext(kind="source", target_id="enterprise") == ENTERPRISE_SOURCE_TARGET
