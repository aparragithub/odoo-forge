from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.data_artifacts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DataArtifactCapability,
    DataArtifactRef,
    DiscardOutcome,
    DiscardOutcomeCode,
    RestoreReadiness,
    RestoreSetComponent,
    RestoreSetManifest,
    ValidationFailureCode,
)


def _component(kind: ArtifactComponentKind) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=kind,
        opaque_component_ref="component-42",
        format_version="v1",
        digest=ArtifactDigest(algorithm="sha256", value="a" * 64),
    )


def test_restore_set_manifest_rejects_missing_identity_format_and_digest_evidence() -> None:
    with pytest.raises(ValidationError):
        RestoreSetManifest(
            restore_set_id="",
            lineage_id="",
            components=(
                RestoreSetComponent(
                    kind=ArtifactComponentKind.DATABASE,
                    opaque_component_ref="database-42",
                    format_version="",
                    digest=ArtifactDigest(algorithm="sha256", value="not-a-digest"),
                ),
                _component(ArtifactComponentKind.FILESTORE),
            ),
        )
    with pytest.raises(ValidationError):
        ArtifactDigest(algorithm="sha256", value="g" * 64)


def test_opaque_and_redacted_contract_fields_reject_connection_details_and_secrets() -> None:
    with pytest.raises(ValidationError):
        RestoreSetComponent(
            kind=ArtifactComponentKind.DATABASE,
            opaque_component_ref="postgres://admin:secret@db.internal/odoo",
            format_version="v1",
            digest=ArtifactDigest(algorithm="sha256", value="a" * 64),
        )
    with pytest.raises(ValidationError):
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=ValidationFailureCode.UNAVAILABLE,
            redacted_detail="token=super-secret",
        )
    with pytest.raises(ValidationError):
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=ValidationFailureCode.UNAVAILABLE,
            redacted_detail="Authorization Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
        )
    with pytest.raises(ValidationError):
        DiscardOutcome(
            code=DiscardOutcomeCode.RESIDUAL_FAILURE,
            residual_ids=("https://storage.internal/artifact",),
        )
    with pytest.raises(ValidationError):
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=ValidationFailureCode.UNAVAILABLE,
            redacted_detail="source db.internal:5432 unavailable",
        )
    with pytest.raises(ValidationError):
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=ValidationFailureCode.UNAVAILABLE,
            redacted_detail="source db.internal unavailable",
        )
    with pytest.raises(ValidationError):
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=ValidationFailureCode.UNAVAILABLE,
            redacted_detail="source [2001:db8::1]:5432 unavailable",
        )


def test_discard_outcome_requires_residual_ids_to_match_its_code() -> None:
    with pytest.raises(ValidationError):
        DiscardOutcome(
            code=DiscardOutcomeCode.COMPLETED,
            residual_ids=("cleanup-42",),
        )
    with pytest.raises(ValidationError):
        DiscardOutcome(code=DiscardOutcomeCode.RESIDUAL_FAILURE)


def test_restore_set_manifest_is_frozen_and_requires_database_and_filestore() -> None:
    manifest = RestoreSetManifest(
        restore_set_id="restore-set-42",
        lineage_id="lineage-42",
        components=(
            _component(ArtifactComponentKind.DATABASE),
            _component(ArtifactComponentKind.FILESTORE),
        ),
    )

    assert manifest.components[0].kind is ArtifactComponentKind.DATABASE
    assert manifest.components[1].kind is ArtifactComponentKind.FILESTORE
    with pytest.raises(ValidationError):
        cast(Any, manifest).lineage_id = "lineage-99"
    with pytest.raises(ValidationError):
        RestoreSetManifest(
            restore_set_id="restore-set-42",
            lineage_id="lineage-42",
            components=(_component(ArtifactComponentKind.DATABASE),),
        )


def test_restore_set_manifest_rejects_duplicate_or_extra_component_membership() -> None:
    with pytest.raises(ValidationError):
        RestoreSetManifest(
            restore_set_id="restore-set-42",
            lineage_id="lineage-42",
            components=(
                _component(ArtifactComponentKind.DATABASE),
                _component(ArtifactComponentKind.DATABASE),
            ),
        )


def test_readiness_and_discard_outcomes_are_typed_and_fail_closed() -> None:
    unavailable = RestoreReadiness(
        ready=False,
        manifest=None,
        failure_code=ValidationFailureCode.UNAVAILABLE,
        redacted_detail="artifact unavailable",
    )
    ready = RestoreReadiness(
        ready=True,
        manifest=RestoreSetManifest(
            restore_set_id="restore-set-42",
            lineage_id="lineage-42",
            components=(
                _component(ArtifactComponentKind.DATABASE),
                _component(ArtifactComponentKind.FILESTORE),
            ),
        ),
        failure_code=None,
        redacted_detail=None,
    )
    residual = DiscardOutcome(
        code=DiscardOutcomeCode.RESIDUAL_FAILURE,
        residual_ids=("cleanup-42",),
        redacted_detail="cleanup deferred",
    )

    assert unavailable.failure_code is ValidationFailureCode.UNAVAILABLE
    assert ready.ready is True
    assert ready.manifest is not None
    assert residual.residual_ids == ("cleanup-42",)
    with pytest.raises(ValidationError):
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=None,
            redacted_detail="untyped failure",
        )
    with pytest.raises(ValidationError) as error:
        DiscardOutcome.model_validate(
            {
                "code": DiscardOutcomeCode.COMPLETED,
                "artifact_bytes": b"restore payload",
            }
        )

    assert "restore payload" not in str(error.value)


def test_data_artifact_ref_remains_an_opaque_string_value() -> None:
    reference = DataArtifactRef("restore-set-42")

    assert reference == "restore-set-42"

    with pytest.raises(ValueError):
        DataArtifactRef("postgres://admin:secret@db.internal/odoo")
    with pytest.raises(ValueError):
        DataArtifactRef("db.internal:5432")
    with pytest.raises(ValueError):
        DataArtifactRef("db.internal")
    with pytest.raises(ValueError):
        DataArtifactRef("db:5432")
    with pytest.raises(ValueError):
        DataArtifactRef("AKIAIOSFODNN7EXAMPLE")


def test_capability_protocol_requires_the_restore_set_lifecycle_operations() -> None:
    class _Capability:
        def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
            raise NotImplementedError

        def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness:
            raise NotImplementedError

        def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
            raise NotImplementedError

    assert isinstance(_Capability(), DataArtifactCapability)
