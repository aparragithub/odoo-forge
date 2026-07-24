"""Store-backed `DataArtifactCapability` and `RestoreByteSource` (design D10, bridge slice B2)."""

from pathlib import Path

import pytest

from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DiscardOutcomeCode,
    RestoreSetComponent,
    RestoreSetManifest,
    ValidationFailureCode,
)
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge_postgres_docker.staged_capability import (
    StagedArtifactCapability,
    make_staged_byte_source,
)
from odoo_forge_postgres_docker.staged_store import (
    FilesystemStagedArtifactStore,
    StagedArtifactIntegrityError,
    StagedArtifactUnavailableError,
)


def _digest_of(payload: bytes) -> ArtifactDigest:
    import hashlib

    return ArtifactDigest(algorithm="sha256", value=hashlib.sha256(payload).hexdigest())


def _write_source(tmp_path: Path, name: str, payload: bytes) -> Path:
    source_path = tmp_path / name
    source_path.write_bytes(payload)
    return source_path


def _manifest_with(
    database_digest: ArtifactDigest, ref: str = "restore-set-alpha"
) -> RestoreSetManifest:
    database_component = RestoreSetComponent(
        kind=ArtifactComponentKind.DATABASE,
        opaque_component_ref="database-alpha",
        format_version="pg_dump-custom-v1",
        digest=database_digest,
    )
    filestore_component = RestoreSetComponent(
        kind=ArtifactComponentKind.FILESTORE,
        opaque_component_ref="filestore-empty-v1",
        format_version="empty-v1",
        digest=_digest_of(b""),
    )
    return RestoreSetManifest(
        restore_set_id=ref,
        lineage_id="lineage-alpha",
        components=(database_component, filestore_component),
    )


def _staged(
    tmp_path: Path, payload: bytes
) -> tuple[FilesystemStagedArtifactStore, RestoreSetManifest, DataArtifactRef]:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    manifest = _manifest_with(digest)
    ref = DataArtifactRef(manifest.restore_set_id)
    store.stage(digest, source_path)
    store.put(ref, manifest)
    return store, manifest, ref


def test_resolve_returns_manifest_from_store(tmp_path: Path) -> None:
    store, manifest, ref = _staged(tmp_path, b"resolve me")
    capability = StagedArtifactCapability(store)

    assert capability.resolve(ref) == manifest


def test_resolve_propagates_unavailable_error_for_unknown_ref(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    capability = StagedArtifactCapability(store)

    with pytest.raises(StagedArtifactUnavailableError):
        capability.resolve(DataArtifactRef("never-put"))


def test_validate_for_restore_is_ready_when_bytes_and_digests_match(tmp_path: Path) -> None:
    store, manifest, ref = _staged(tmp_path, b"ready bytes")
    capability = StagedArtifactCapability(store)

    readiness = capability.validate_for_restore(ref)

    assert readiness.ready is True
    assert readiness.manifest == manifest
    assert readiness.failure_code is None


def test_validate_for_restore_returns_unavailable_when_manifest_absent(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    capability = StagedArtifactCapability(store)

    readiness = capability.validate_for_restore(DataArtifactRef("never-put"))

    assert readiness.ready is False
    assert readiness.manifest is None
    assert readiness.failure_code is ValidationFailureCode.UNAVAILABLE


def test_validate_for_restore_returns_unavailable_when_database_blob_missing(
    tmp_path: Path,
) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    manifest = _manifest_with(_digest_of(b"never staged"))
    ref = DataArtifactRef(manifest.restore_set_id)
    store.put(ref, manifest)
    capability = StagedArtifactCapability(store)

    readiness = capability.validate_for_restore(ref)

    assert readiness.ready is False
    assert readiness.manifest is None
    assert readiness.failure_code is ValidationFailureCode.UNAVAILABLE


def test_validate_for_restore_returns_integrity_failed_on_tampered_bytes(tmp_path: Path) -> None:
    store, manifest, ref = _staged(tmp_path, b"original bytes for tampering")
    database_component = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    blob_path = store.root / "blobs" / f"sha256-{database_component.digest.value}.bin"
    blob_path.chmod(0o600)
    blob_path.write_bytes(b"corrupted replacement bytes for the staged dump")
    blob_path.chmod(0o600)
    capability = StagedArtifactCapability(store)

    readiness = capability.validate_for_restore(ref)

    assert readiness.ready is False
    assert readiness.manifest is None
    assert readiness.failure_code is ValidationFailureCode.INTEGRITY_FAILED


def test_discard_delegates_to_store(tmp_path: Path) -> None:
    store, _manifest, ref = _staged(tmp_path, b"discard me")
    capability = StagedArtifactCapability(store)

    outcome = capability.discard(ref)

    assert outcome.code is DiscardOutcomeCode.COMPLETED
    with pytest.raises(StagedArtifactUnavailableError):
        store.resolve(ref)


def test_make_staged_byte_source_resolves_a_readable_path(tmp_path: Path) -> None:
    store, manifest, _ref = _staged(tmp_path, b"byte source bytes")
    database_component = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    byte_source = make_staged_byte_source(store)

    resolved_path = byte_source(database_component)

    assert resolved_path.read_bytes() == b"byte source bytes"


def test_make_staged_byte_source_refuses_a_digest_mismatched_component(tmp_path: Path) -> None:
    store, manifest, _ref = _staged(tmp_path, b"tamper target bytes")
    database_component = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    blob_path = store.root / "blobs" / f"sha256-{database_component.digest.value}.bin"
    blob_path.chmod(0o600)
    blob_path.write_bytes(b"a different payload replacing the staged dump entirely")
    blob_path.chmod(0o600)
    byte_source = make_staged_byte_source(store)

    with pytest.raises(StagedArtifactIntegrityError):
        byte_source(database_component)


def test_make_staged_byte_source_raises_unavailable_when_blob_absent(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    manifest = _manifest_with(_digest_of(b"never staged for byte source"))
    database_component = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    byte_source = make_staged_byte_source(store)

    with pytest.raises(StagedArtifactUnavailableError):
        byte_source(database_component)
