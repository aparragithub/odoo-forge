import pytest
from pydantic import ValidationError

from odoo_forge.anonymization.apply import (
    AnonymizationOutcome,
    apply_anonymization,
    record_anonymization_exception,
)
from odoo_forge.anonymization.policy import AnonymizationPolicy, AnonymizationRule, MaskStrategy
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
    RestoreSetManifest,
)


def _component(kind: ArtifactComponentKind, ref: str) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=kind,
        opaque_component_ref=ref,
        format_version="v1",
        digest=ArtifactDigest(algorithm="sha256", value="a" * 64),
    )


def _manifest() -> RestoreSetManifest:
    return RestoreSetManifest(
        restore_set_id="restore-set-42",
        lineage_id="lineage-42",
        components=(
            _component(ArtifactComponentKind.DATABASE, "database-42"),
            _component(ArtifactComponentKind.FILESTORE, "filestore-42"),
        ),
    )


def _masked_component(
    component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
) -> RestoreSetComponent:
    assert rules
    return component.model_copy(update={"opaque_component_ref": "database-42-masked"})


def _identity_mask_transform(
    component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
) -> RestoreSetComponent:
    return component


def test_apply_anonymization_masks_only_the_database_component_by_default() -> None:
    policy = AnonymizationPolicy(
        rules=(
            AnonymizationRule(table="res_partner", column="email", mask_strategy=MaskStrategy.HASH),
        )
    )

    outcome = apply_anonymization(_manifest(), policy, mask_transform=_masked_component)

    assert isinstance(outcome, AnonymizationOutcome)
    database_component = next(
        component
        for component in outcome.manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    filestore_component = next(
        component
        for component in outcome.manifest.components
        if component.kind is ArtifactComponentKind.FILESTORE
    )
    assert database_component.opaque_component_ref == "database-42-masked"
    assert filestore_component.opaque_component_ref == "filestore-42"


def test_apply_anonymization_emits_applied_evidence_bound_to_the_lineage() -> None:
    policy = AnonymizationPolicy()

    outcome = apply_anonymization(_manifest(), policy, mask_transform=_identity_mask_transform)

    assert outcome.evidence.event == "anonymization_applied"
    assert outcome.evidence.references == ("lineage-42",)
    assert "secret" not in outcome.evidence.summary


def test_record_anonymization_exception_leaves_the_manifest_raw_and_unchanged() -> None:
    manifest = _manifest()

    outcome = record_anonymization_exception(manifest, reason="approved manual QA exception")

    assert outcome.manifest == manifest
    assert outcome.evidence.event == "anonymization_exception"
    assert outcome.evidence.references == ("lineage-42",)
    assert outcome.evidence.summary == "approved manual QA exception"


def test_record_anonymization_exception_rejects_a_sensitive_reason() -> None:
    with pytest.raises(ValidationError):
        record_anonymization_exception(_manifest(), reason="token=super-secret")
