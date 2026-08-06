from datetime import UTC, datetime

import pytest

from odoo_forge.anonymization.policy import AnonymizationPolicy, AnonymizationRule, MaskStrategy
from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DiscardOutcome,
    DiscardOutcomeCode,
    RestoreReadiness,
    RestoreSetComponent,
    RestoreSetManifest,
    ValidationFailureCode,
)
from odoo_forge.data_artifacts.coordinator import (
    CaptureIntegrityError,
    CaptureNotReadyError,
    DataArtifactCopyCoordinator,
    RawDeliveryRefusedError,
)
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.data_environments.types import RawDataGrant
from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
)
from odoo_forge.durable_operations.types import (
    DurableOperationIdentity,
    LifecycleState,
    RedactedEvidence,
)
from odoo_forge.resource_ownership.types import OperationIdentity, ResourceOwnership


def _component(kind: ArtifactComponentKind, ref: str) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=kind,
        opaque_component_ref=ref,
        format_version="v1",
        digest=ArtifactDigest(algorithm="sha256", value="a" * 64),
    )


def _manifest(
    restore_set_id: str = "restore-set-42", lineage_id: str = "lineage-42"
) -> RestoreSetManifest:
    return RestoreSetManifest(
        restore_set_id=restore_set_id,
        lineage_id=lineage_id,
        components=(
            _component(ArtifactComponentKind.DATABASE, "database-42"),
            _component(ArtifactComponentKind.FILESTORE, "filestore-42"),
        ),
    )


def _identity_mask_transform(
    component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
) -> RestoreSetComponent:
    return component


class _FakeCaptureCapability:
    def __init__(self, manifest: RestoreSetManifest) -> None:
        self._manifest = manifest
        self.capture_calls: list[CaptureSource] = []

    def capture(self, source: CaptureSource) -> RestoreSetManifest:
        self.capture_calls.append(source)
        return self._manifest


class _FakeArtifactCapability:
    def __init__(self, readiness: RestoreReadiness, *, discard_raises: bool = False) -> None:
        self._readiness = readiness
        self._discard_raises = discard_raises
        self.validated_refs: list[DataArtifactRef] = []
        self.discarded_refs: list[DataArtifactRef] = []

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        raise NotImplementedError

    def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness:
        self.validated_refs.append(ref)
        return self._readiness

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        self.discarded_refs.append(ref)
        if self._discard_raises:
            raise RuntimeError("staged ref discard backend unavailable")
        return DiscardOutcome(code=DiscardOutcomeCode.COMPLETED)


class _FakeDatabaseProvider:
    def __init__(self, creation: DatabaseCreation) -> None:
        self._creation = creation
        self.restore_calls: list[tuple[DatabaseSpec, DataArtifactRef, CredentialHandle]] = []

    def restore(
        self, spec: DatabaseSpec, artifact: DataArtifactRef, credentials: CredentialHandle
    ) -> DatabaseCreation:
        self.restore_calls.append((spec, artifact, credentials))
        return self._creation

    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        raise NotImplementedError

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        raise NotImplementedError

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        raise NotImplementedError

    def delete(self, creation: DatabaseCreation) -> None:
        raise NotImplementedError

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        raise NotImplementedError


def _creation() -> DatabaseCreation:
    return DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="operation-42"), owned_resource_ids=("database-42",)
        ),
    )


def _ready_readiness() -> RestoreReadiness:
    return RestoreReadiness(
        ready=True, manifest=_manifest(), failure_code=None, redacted_detail=None
    )


def _integrity_failed_readiness() -> RestoreReadiness:
    return RestoreReadiness(
        ready=False,
        manifest=None,
        failure_code=ValidationFailureCode.INTEGRITY_FAILED,
        redacted_detail="digest mismatch",
    )


def _source() -> CaptureSource:
    return CaptureSource(
        credentials=CredentialHandle("source-credential"),
        target=TargetContext(kind="source", target_id="live-source"),
    )


def _operation() -> DurableOperationIdentity:
    return DurableOperationIdentity(operation_id="operation-42", request_digest="digest-42")


def _policy() -> AnonymizationPolicy:
    return AnonymizationPolicy(
        rules=(
            AnonymizationRule(table="res_partner", column="email", mask_strategy=MaskStrategy.HASH),
        )
    )


def test_happy_path_captures_anonymizes_and_delivers_with_checkpoints() -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(_ready_readiness())
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
    )

    result = coordinator.run(
        source=_source(),
        spec=DatabaseSpec(name="database-42"),
        policy=_policy(),
        credentials=CredentialHandle("target-credential"),
        operation=_operation(),
    )

    assert result.state is LifecycleState.SUCCEEDED
    assert [checkpoint.phase for checkpoint in result.checkpoints] == [
        "captured",
        "anonymized",
        "integrity_verified",
    ]
    assert result.checkpoints[1].evidence.event == "anonymization_applied"
    assert database_provider.restore_calls == [
        (
            DatabaseSpec(name="database-42"),
            DataArtifactRef("restore-set-42"),
            CredentialHandle("target-credential"),
        )
    ]
    assert result.creation.ref.identifier == "database-42"


def _raw_grant(**updates: object) -> RawDataGrant:
    return RawDataGrant(
        operation_id="operation-42",
        environment_id="qa",
        grantor="operator",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        reason="approved",
        audit_reference="audit-42",
    ).model_copy(update=updates)


@pytest.mark.parametrize(
    "grant",
    [
        None,
        _raw_grant(operation_id="other"),
        _raw_grant(environment_id="other"),
        _raw_grant(expires_at=datetime(2020, 1, 1, tzinfo=UTC)),
    ],
)
def test_raw_delivery_refused_without_a_valid_grant(grant: RawDataGrant | None) -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(_ready_readiness())
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
        audited_exception_lookup=lambda lineage_id: RedactedEvidence(
            event="anonymization_exception",
            summary="legacy unscoped evidence",
            references=(lineage_id,),
        ),
    )

    with pytest.raises(RawDeliveryRefusedError):
        coordinator.run(
            source=_source(),
            spec=DatabaseSpec(name="database-42"),
            policy=_policy(),
            credentials=CredentialHandle("target-credential"),
            operation=_operation(),
            request_raw_delivery=True,
            raw_grant=grant,
            raw_grant_environment_id="qa",
        )

    assert database_provider.restore_calls == []


def test_raw_delivery_permitted_with_a_matching_audited_grant() -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(_ready_readiness())
    database_provider = _FakeDatabaseProvider(_creation())
    grant = RedactedEvidence(
        event="anonymization_exception",
        summary="approved manual QA exception",
        references=("lineage-42",),
    )
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
        audited_exception_lookup=lambda lineage_id: grant if lineage_id == "lineage-42" else None,
    )

    result = coordinator.run(
        source=_source(),
        spec=DatabaseSpec(name="database-42"),
        policy=_policy(),
        credentials=CredentialHandle("target-credential"),
        operation=_operation(),
        request_raw_delivery=True,
        raw_grant=_raw_grant(),
        raw_grant_environment_id="qa",
    )

    assert result.checkpoints[1].evidence.event == "anonymization_exception"
    assert len(database_provider.restore_calls) == 1


def test_integrity_mismatch_raises_and_cleans_up_without_delivering() -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(_integrity_failed_readiness())
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
    )

    with pytest.raises(CaptureIntegrityError) as excinfo:
        coordinator.run(
            source=_source(),
            spec=DatabaseSpec(name="database-42"),
            policy=_policy(),
            credentials=CredentialHandle("target-credential"),
            operation=_operation(),
        )

    assert excinfo.value.failure_code is ValidationFailureCode.INTEGRITY_FAILED
    assert database_provider.restore_calls == []
    assert artifact_capability.discarded_refs == [DataArtifactRef("restore-set-42")]
    assert coordinator.last_state is LifecycleState.CLEANUP_REQUIRED


def test_compensation_discard_failure_does_not_mask_original_error() -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(
        _integrity_failed_readiness(), discard_raises=True
    )
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
    )

    with pytest.raises(CaptureIntegrityError) as excinfo:
        coordinator.run(
            source=_source(),
            spec=DatabaseSpec(name="database-42"),
            policy=_policy(),
            credentials=CredentialHandle("target-credential"),
            operation=_operation(),
        )

    assert excinfo.value.failure_code is ValidationFailureCode.INTEGRITY_FAILED
    assert coordinator.last_state is LifecycleState.CLEANUP_REQUIRED


def test_non_integrity_readiness_failure_carries_actual_failure_code() -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=ValidationFailureCode.UNAVAILABLE,
            redacted_detail=None,
        )
    )
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
    )

    with pytest.raises(CaptureNotReadyError) as excinfo:
        coordinator.run(
            source=_source(),
            spec=DatabaseSpec(name="database-42"),
            policy=_policy(),
            credentials=CredentialHandle("target-credential"),
            operation=_operation(),
        )

    assert excinfo.value.failure_code is ValidationFailureCode.UNAVAILABLE
    assert database_provider.restore_calls == []


def test_raw_delivery_refused_when_grant_lineage_does_not_match() -> None:
    capture_capability = _FakeCaptureCapability(_manifest())
    artifact_capability = _FakeArtifactCapability(_ready_readiness())
    database_provider = _FakeDatabaseProvider(_creation())
    mismatched_grant = RedactedEvidence(
        event="anonymization_exception",
        summary="approved manual QA exception for a different lineage",
        references=("other-lineage",),
    )
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_identity_mask_transform,
        audited_exception_lookup=lambda lineage_id: mismatched_grant,
    )

    with pytest.raises(RawDeliveryRefusedError):
        coordinator.run(
            source=_source(),
            spec=DatabaseSpec(name="database-42"),
            policy=_policy(),
            credentials=CredentialHandle("target-credential"),
            operation=_operation(),
            request_raw_delivery=True,
        )

    assert database_provider.restore_calls == []
