"""Bridge slice B4: anonymize-re-store consistency (D11) + discard-on-success GC (D12).

Uses the REAL `FilesystemStagedArtifactStore` + `StagedArtifactCapability` +
`make_staged_byte_source` (bridge slices B1/B2) wired directly into
`DataArtifactCopyCoordinator`, with fakes only for capture and the database
provider — so these tests exercise actual staged bytes on disk, not just
in-memory doubles.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from odoo_forge.anonymization.apply import MaskTransform
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
)
from odoo_forge.data_artifacts.coordinator import (
    AnonymizationConsistencyError,
    CoordinatedCopyResult,
    DataArtifactCopyCoordinator,
)
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
)
from odoo_forge.durable_operations.types import DurableOperationIdentity, LifecycleState
from odoo_forge.resource_ownership.types import OperationIdentity, ResourceOwnership
from odoo_forge_postgres_docker.restore_target import make_docker_restore_target
from odoo_forge_postgres_docker.staged_capability import (
    StagedArtifactCapability,
    make_staged_byte_source,
)
from odoo_forge_postgres_docker.staged_store import (
    FilesystemStagedArtifactStore,
    StagedArtifactUnavailableError,
)

_RESTORE_SET_ID = "restore-set-42"
_LINEAGE_ID = "lineage-42"


def _digest_of(payload: bytes) -> ArtifactDigest:
    return ArtifactDigest(algorithm="sha256", value=hashlib.sha256(payload).hexdigest())


def _component(
    kind: ArtifactComponentKind, ref: str, digest: ArtifactDigest
) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=kind, opaque_component_ref=ref, format_version="v1", digest=digest
    )


def _manifest_with_database_digest(digest: ArtifactDigest) -> RestoreSetManifest:
    return RestoreSetManifest(
        restore_set_id=_RESTORE_SET_ID,
        lineage_id=_LINEAGE_ID,
        components=(
            _component(ArtifactComponentKind.DATABASE, "database-42", digest),
            _component(ArtifactComponentKind.FILESTORE, "filestore-42", _digest_of(b"")),
        ),
    )


class _FakeCaptureCapability:
    """Simulates B3: capture already persisted the RAW manifest into the store."""

    def __init__(self, manifest: RestoreSetManifest) -> None:
        self._manifest = manifest

    def capture(self, source: CaptureSource) -> RestoreSetManifest:
        return self._manifest


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


def _stage_raw_manifest(
    store: FilesystemStagedArtifactStore, tmp_path: Path, raw_payload: bytes
) -> RestoreSetManifest:
    raw_digest = _digest_of(raw_payload)
    manifest = _manifest_with_database_digest(raw_digest)
    source_path = tmp_path / "raw-dump"
    source_path.write_bytes(raw_payload)
    store.stage(raw_digest, source_path)
    store.put(DataArtifactRef(_RESTORE_SET_ID), manifest)
    return manifest


def _make_masking_transform(
    store: FilesystemStagedArtifactStore, tmp_path: Path, masked_payload: bytes
) -> MaskTransform:
    """A `MaskTransform` double that stages NEW masked bytes into the SAME store (design D11)."""

    def _mask(
        component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
    ) -> RestoreSetComponent:
        masked_digest = _digest_of(masked_payload)
        masked_source = tmp_path / "masked-dump"
        masked_source.write_bytes(masked_payload)
        store.stage(masked_digest, masked_source)
        return _component(component.kind, component.opaque_component_ref, masked_digest)

    return _mask


def _build_coordinator(
    *,
    store: FilesystemStagedArtifactStore,
    capture_manifest: RestoreSetManifest,
    mask_transform: MaskTransform,
    database_provider: _FakeDatabaseProvider,
) -> DataArtifactCopyCoordinator:
    return DataArtifactCopyCoordinator(
        capture_capability=_FakeCaptureCapability(capture_manifest),
        artifact_capability=StagedArtifactCapability(store),
        database_provider=database_provider,
        mask_transform=mask_transform,
        manifest_persistence=store.put,
    )


def _run(
    coordinator: DataArtifactCopyCoordinator, *, retain_staged: bool = False
) -> CoordinatedCopyResult:
    return coordinator.run(
        source=_source(),
        spec=DatabaseSpec(name="database-42"),
        policy=_policy(),
        credentials=CredentialHandle("target-credential"),
        operation=_operation(),
        retain_staged=retain_staged,
    )


def test_anonymize_re_store_keeps_delivered_manifest_digest_consistent_with_stored_bytes(
    tmp_path: Path,
) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")
    masked_payload = b"masked-bytes"
    mask_transform = _make_masking_transform(store, tmp_path, masked_payload)
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=mask_transform,
        database_provider=database_provider,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    stored_manifest = store.resolve(DataArtifactRef(_RESTORE_SET_ID))
    database_component = next(
        component
        for component in stored_manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert database_component.digest.value == _digest_of(masked_payload).value
    assert database_component.digest.value != _digest_of(b"raw-pii-bytes").value
    # The delivered digest must resolve REAL bytes through the store, not a stale record.
    resolved_path = store.open_component(database_component)
    assert resolved_path.read_bytes() == masked_payload


def test_no_op_manifest_persistence_with_non_identity_mask_fails_closed(tmp_path: Path) -> None:
    """CRITICAL fix R4-001, WITHOUT a required-param signature change: `manifest_persistence`
    stays OPTIONAL (default a no-op), so a coordinator built without it is still constructible
    (the pre-existing `test_coordinator.py` fakes rely on this). With a REAL (digest-changing)
    mask and that no-op default, the store still serves the RAW manifest under `ref` — the
    coordinator's internal D11 consistency check must detect the served/masked digest mismatch
    and fail closed BEFORE delivery, instead of silently delivering raw bytes under an
    `anonymization_applied` checkpoint (the bypass)."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_payload = b"raw-pii-bytes"
    raw_manifest = _stage_raw_manifest(store, tmp_path, raw_payload)
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=_FakeCaptureCapability(raw_manifest),
        artifact_capability=StagedArtifactCapability(store),
        database_provider=database_provider,
        mask_transform=mask_transform,
        # `manifest_persistence` deliberately omitted: it must default to a no-op.
    )

    with pytest.raises(AnonymizationConsistencyError):
        _run(coordinator)

    assert database_provider.restore_calls == []
    assert coordinator.last_state is LifecycleState.CLEANUP_REQUIRED


def test_wired_manifest_persistence_with_real_mask_keeps_consistency_and_delivers(
    tmp_path: Path,
) -> None:
    """Companion to the fail-closed test above: once `manifest_persistence` is wired to the
    same store (the real-caller wiring), the served manifest's digest matches the masked
    digest and the D11 consistency check is a no-op that lets delivery proceed."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=mask_transform,
        database_provider=database_provider,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    assert len(database_provider.restore_calls) == 1


def test_anonymize_re_store_reaps_the_orphaned_raw_pre_mask_blob(tmp_path: Path) -> None:
    """CRITICAL fix: after a full anonymize+deliver+success-GC, NO unmasked raw blob may
    remain in the store. Inspects the REAL blobs directory on disk, not just `resolve(ref)`
    (a raw blob can be orphaned — unreferenced by any manifest — yet still sit on disk)."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_payload = b"raw-pii-bytes"
    raw_manifest = _stage_raw_manifest(store, tmp_path, raw_payload)
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=mask_transform,
        database_provider=database_provider,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    raw_digest = _digest_of(raw_payload)
    raw_blob_path = store.root / "blobs" / f"{raw_digest.algorithm}-{raw_digest.value}.bin"
    assert not raw_blob_path.exists()


def test_shadow_ref_is_discarded_even_when_the_real_ref_persist_raises(tmp_path: Path) -> None:
    """RED test for the try/finally hardening: if `manifest_persistence(ref, masked)` faults
    AFTER `manifest_persistence(shadow_ref, raw)` already succeeded, the shadow manifest must
    still be reaped (no leaked shadow manifest, and therefore no lingering raw-PII blob path
    left dangling), and the original fault must propagate unchanged."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_payload = b"raw-pii-bytes"
    raw_manifest = _stage_raw_manifest(store, tmp_path, raw_payload)
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    real_ref = DataArtifactRef(_RESTORE_SET_ID)
    shadow_ref = DataArtifactRef(f"{_RESTORE_SET_ID}-preanonymize-raw")

    class _RealRefPersistFault(RuntimeError):
        pass

    def _faulty_persistence(persist_ref: DataArtifactRef, manifest: RestoreSetManifest) -> None:
        if persist_ref == real_ref:
            raise _RealRefPersistFault("simulated fault persisting the masked manifest")
        store.put(persist_ref, manifest)

    coordinator = DataArtifactCopyCoordinator(
        capture_capability=_FakeCaptureCapability(raw_manifest),
        artifact_capability=StagedArtifactCapability(store),
        database_provider=database_provider,
        mask_transform=mask_transform,
        manifest_persistence=_faulty_persistence,
    )

    with pytest.raises(_RealRefPersistFault):
        _run(coordinator)

    assert database_provider.restore_calls == []
    with pytest.raises(StagedArtifactUnavailableError):
        store.resolve(shadow_ref)


def test_pass_through_masking_leaves_the_unchanged_blob_resolvable(tmp_path: Path) -> None:
    """When v1 masking is a pass-through re-stamp (same bytes/digest), the raw-blob reap
    must be a no-op: the (only) blob is still "referenced elsewhere" via the re-stored
    manifest under the real `ref`, so it must remain resolvable, not be reaped as if
    orphaned."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"unchanged-bytes")

    def _identity_mask(
        component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
    ) -> RestoreSetComponent:
        return component

    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=_identity_mask,
        database_provider=database_provider,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    stored_manifest = store.resolve(DataArtifactRef(_RESTORE_SET_ID))
    database_component = next(
        component
        for component in stored_manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    resolved_path = store.open_component(database_component)
    assert resolved_path.read_bytes() == b"unchanged-bytes"


class _ForcedDiscardArtifactCapability:
    """Wraps a real `StagedArtifactCapability`, forcing a specific discard behavior (a
    non-raising `RESIDUAL_FAILURE`, or a raised exception) only for ONE forced ref, so
    the other reap in the same run behaves normally (RED tests for both residual-recording
    paths: the D12 discard-on-success GC and the shadow-ref raw-blob reap)."""

    def __init__(
        self,
        inner: StagedArtifactCapability,
        *,
        forced_ref: DataArtifactRef,
        raise_instead: bool = False,
    ) -> None:
        self._inner = inner
        self._forced_ref = forced_ref
        self._raise_instead = raise_instead

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        return self._inner.resolve(ref)

    def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness:
        return self._inner.validate_for_restore(ref)

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        if ref == self._forced_ref:
            if self._raise_instead:
                raise RuntimeError("simulated forced discard fault")
            return DiscardOutcome(
                code=DiscardOutcomeCode.RESIDUAL_FAILURE, residual_ids=("database-42",)
            )
        return self._inner.discard(ref)


@pytest.mark.parametrize("raise_instead", [False, True])
def test_discard_on_success_residual_is_recorded_as_a_checkpoint(
    tmp_path: Path, raise_instead: bool
) -> None:
    """WARNING fix: BOTH a non-raising `RESIDUAL_FAILURE` AND a raised exception from the
    D12 discard-on-success GC must be recorded as durable checkpoint/evidence — neither may
    be silently dropped."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    artifact_capability = _ForcedDiscardArtifactCapability(
        StagedArtifactCapability(store),
        forced_ref=DataArtifactRef(_RESTORE_SET_ID),
        raise_instead=raise_instead,
    )
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=_FakeCaptureCapability(raw_manifest),
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=mask_transform,
        manifest_persistence=store.put,
    )

    result = _run(coordinator)

    assert result.state is LifecycleState.SUCCEEDED
    assert any(
        checkpoint.evidence.event == "discard_on_success_residual"
        for checkpoint in result.checkpoints
    )


@pytest.mark.parametrize("raise_instead", [False, True])
def test_raw_reap_residual_is_recorded_as_a_checkpoint(tmp_path: Path, raise_instead: bool) -> None:
    """CRITICAL fix: the digest-changing shadow-ref raw-blob reap must record a durable
    checkpoint when the reap itself leaves a `RESIDUAL_FAILURE` OR when the discard call
    raises — a leaked raw (unmasked PII) blob with no durable trace must never happen."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    shadow_ref = DataArtifactRef(f"{_RESTORE_SET_ID}-preanonymize-raw")
    artifact_capability = _ForcedDiscardArtifactCapability(
        StagedArtifactCapability(store), forced_ref=shadow_ref, raise_instead=raise_instead
    )
    coordinator = DataArtifactCopyCoordinator(
        capture_capability=_FakeCaptureCapability(raw_manifest),
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=mask_transform,
        manifest_persistence=store.put,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    assert any(
        checkpoint.evidence.event == "raw_reap_residual" for checkpoint in result.checkpoints
    )


def test_shared_filestore_blob_survives_the_digest_changing_raw_reap(tmp_path: Path) -> None:
    """WARNING gap closed: proves — with a REAL shared blob, not prose — that the
    digest-changing raw reap preserves a component staged and referenced elsewhere in the
    SAME manifest (here, filestore), while the raw pre-mask database blob is reaped."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_digest = _digest_of(b"raw-pii-bytes")
    filestore_digest = _digest_of(b"filestore-bytes")
    manifest = RestoreSetManifest(
        restore_set_id=_RESTORE_SET_ID,
        lineage_id=_LINEAGE_ID,
        components=(
            _component(ArtifactComponentKind.DATABASE, "database-42", raw_digest),
            _component(ArtifactComponentKind.FILESTORE, "filestore-42", filestore_digest),
        ),
    )
    (tmp_path / "raw-dump").write_bytes(b"raw-pii-bytes")
    store.stage(raw_digest, tmp_path / "raw-dump")
    (tmp_path / "filestore-dump").write_bytes(b"filestore-bytes")
    store.stage(filestore_digest, tmp_path / "filestore-dump")
    store.put(DataArtifactRef(_RESTORE_SET_ID), manifest)
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=manifest,
        mask_transform=mask_transform,
        database_provider=database_provider,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    filestore_blob_path = (
        store.root / "blobs" / f"{filestore_digest.algorithm}-{filestore_digest.value}.bin"
    )
    assert filestore_blob_path.exists()
    raw_blob_path = store.root / "blobs" / f"{raw_digest.algorithm}-{raw_digest.value}.bin"
    assert not raw_blob_path.exists()


def test_discard_on_success_removes_staged_bytes_by_default(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=mask_transform,
        database_provider=database_provider,
    )

    result = _run(coordinator)

    assert result.state is LifecycleState.SUCCEEDED
    with pytest.raises(StagedArtifactUnavailableError):
        store.resolve(DataArtifactRef(_RESTORE_SET_ID))


def test_retain_staged_opts_out_of_discard_on_success(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")
    mask_transform = _make_masking_transform(store, tmp_path, b"masked-bytes")
    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=mask_transform,
        database_provider=database_provider,
    )

    result = _run(coordinator, retain_staged=True)

    assert result.state is LifecycleState.SUCCEEDED
    # Still resolvable: retain_staged=True opted out of the D12 discard-on-success GC.
    store.resolve(DataArtifactRef(_RESTORE_SET_ID))


def test_failure_path_still_discards_staged_bytes_via_real_store(tmp_path: Path) -> None:
    """The pre-existing on-failure compensation discard (unaffected by D12) still frees
    real staged bytes when integrity verification fails."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    raw_manifest = _stage_raw_manifest(store, tmp_path, b"raw-pii-bytes")

    def _tampering_mask_transform(
        component: RestoreSetComponent, rules: tuple[AnonymizationRule, ...]
    ) -> RestoreSetComponent:
        # Return a component whose digest matches NOTHING staged -> integrity fails.
        return _component(
            component.kind, component.opaque_component_ref, _digest_of(b"never-staged")
        )

    database_provider = _FakeDatabaseProvider(_creation())
    coordinator = _build_coordinator(
        store=store,
        capture_manifest=raw_manifest,
        mask_transform=_tampering_mask_transform,
        database_provider=database_provider,
    )

    with pytest.raises(Exception):  # noqa: B017 - CaptureIntegrityError, verified via state below
        _run(coordinator)

    assert coordinator.last_state is LifecycleState.CLEANUP_REQUIRED
    with pytest.raises(StagedArtifactUnavailableError):
        store.resolve(DataArtifactRef(_RESTORE_SET_ID))


def test_store_wiring_restore_target_reads_real_staged_bytes_via_byte_source(
    tmp_path: Path,
) -> None:
    """Bridge slice B4 store wiring: `make_staged_byte_source` + `make_docker_restore_target`
    resolve and stream the REAL staged bytes for a component, end to end (fake subprocess
    runner only, to avoid a real `docker`/`pg_restore` dependency)."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"streamed-restore-bytes"
    digest = _digest_of(payload)
    source_path = tmp_path / "dump"
    source_path.write_bytes(payload)
    store.stage(digest, source_path)
    component = _component(ArtifactComponentKind.DATABASE, "database-42", digest)

    byte_source = make_staged_byte_source(store)
    seen_stdin_bytes: list[bytes] = []

    def _fake_runner(
        argv: Sequence[str], *, stdin_path: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        seen_stdin_bytes.append(stdin_path.read_bytes())
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    restore_target = make_docker_restore_target(byte_source=byte_source, runner=_fake_runner)

    assert restore_target(component, "database-42") is True
    assert seen_stdin_bytes == [payload]
