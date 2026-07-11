from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.credentials import CredentialHandle
from odoo_forge.credentials.types import CredentialHandle as CredentialHandleType
from odoo_forge.data_artifacts import DataArtifactRef
from odoo_forge.data_artifacts.types import DataArtifactRef as DataArtifactRefType
from odoo_forge.database import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
    OperationIdentity,
    ResourceOwnership,
)


def _receipt() -> CreationReceipt:
    return CreationReceipt(
        operation=OperationIdentity(value="provision-42"),
        owned_resource_ids=("database-42",),
    )


def test_database_creation_is_an_immutable_reference_and_receipt_handoff() -> None:
    ref = DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED)
    receipt = _receipt()

    creation = DatabaseCreation(ref=ref, receipt=receipt)

    assert creation.ref == ref
    assert creation.receipt == receipt
    with pytest.raises(ValidationError):
        cast(Any, creation).ref = DatabaseRef(
            identifier="database-99", ownership=ResourceOwnership.CREATED
        )


def test_provider_values_are_frozen() -> None:
    spec = DatabaseSpec(name="analytics")
    report = CleanupReport(residual_failures=("network-42",))

    with pytest.raises(ValidationError):
        cast(Any, spec).name = "reporting"
    with pytest.raises(ValidationError):
        cast(Any, report).residual_failures = ()


def test_provider_values_reject_secret_or_artifact_payload_fields() -> None:
    with pytest.raises(ValidationError):
        DatabaseSpec.model_validate({"name": "analytics", "credential_secret": "super-secret"})
    with pytest.raises(ValidationError):
        DatabaseRef.model_validate(
            {
                "identifier": "database-42",
                "ownership": ResourceOwnership.CREATED,
                "artifact_bytes": b"database dump",
            }
        )


def test_ownership_values_are_limited_to_the_provider_lifecycle_categories() -> None:
    assert {ownership.value for ownership in ResourceOwnership} == {
        "created",
        "adopted",
        "external",
    }


def test_opaque_cross_capability_references_are_re_exported_without_payload_access() -> None:
    credentials = CredentialHandle("credential-42")
    artifact = DataArtifactRef("artifact-42")

    assert CredentialHandle is CredentialHandleType
    assert DataArtifactRef is DataArtifactRefType
    assert credentials == "credential-42"
    assert artifact == "artifact-42"
