"""Custody, content-addressing, and integrity regressions for the filesystem staging store."""

import json
import stat
from pathlib import Path

import pytest

from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DiscardOutcomeCode,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge_postgres_docker.staged_store import (
    FilesystemStagedArtifactStore,
    StagedArtifactCustodyError,
    StagedArtifactIntegrityError,
    StagedArtifactStateError,
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


def test_stage_put_resolve_open_component_round_trip(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"pg_dump bytes for alpha"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    manifest = _manifest_with(digest)
    ref = DataArtifactRef(manifest.restore_set_id)

    store.stage(digest, source_path)
    store.put(ref, manifest)

    resolved = store.resolve(ref)
    assert resolved == manifest
    assert not source_path.exists()

    database_component = next(
        component
        for component in resolved.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    opened_path = store.open_component(database_component)
    assert opened_path.read_bytes() == payload


def test_stage_is_content_addressed_and_dedups(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"identical bytes"
    digest = _digest_of(payload)
    first_source = _write_source(tmp_path, "first", payload)
    second_source = _write_source(tmp_path, "second", payload)

    store.stage(digest, first_source)
    store.stage(digest, second_source)

    blob_path = tmp_path / "artifact-store" / "blobs" / f"sha256-{digest.value}.bin"
    assert blob_path.read_bytes() == payload
    assert not first_source.exists()
    assert not second_source.exists()


def test_directories_and_files_use_private_custody_modes(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"custody bytes"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    manifest = _manifest_with(digest)
    ref = DataArtifactRef(manifest.restore_set_id)

    store.stage(digest, source_path)
    store.put(ref, manifest)

    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE((store.root / "blobs").stat().st_mode) == 0o700
    assert stat.S_IMODE((store.root / "manifests").stat().st_mode) == 0o700
    blob_path = store.root / "blobs" / f"sha256-{digest.value}.bin"
    manifest_path = store.root / "manifests" / f"{ref}.json"
    assert stat.S_IMODE(blob_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600


def test_open_component_rejects_permissive_blob_custody(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"loosened custody bytes"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    store.stage(digest, source_path)
    blob_path = store.root / "blobs" / f"sha256-{digest.value}.bin"
    blob_path.chmod(0o644)
    manifest = _manifest_with(digest)
    database_component = manifest.components[0]

    with pytest.raises(StagedArtifactCustodyError):
        store.open_component(database_component)


def test_open_component_rejects_symlinked_blob(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"symlink target bytes"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    store.stage(digest, source_path)
    blob_path = store.root / "blobs" / f"sha256-{digest.value}.bin"
    real_target = tmp_path / "outside-target.bin"
    real_target.write_bytes(payload)
    blob_path.unlink()
    blob_path.symlink_to(real_target)
    manifest = _manifest_with(digest)
    database_component = manifest.components[0]

    with pytest.raises(StagedArtifactCustodyError):
        store.open_component(database_component)


def test_open_component_raises_unavailable_when_blob_absent(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    manifest = _manifest_with(_digest_of(b"never staged"))
    database_component = manifest.components[0]

    with pytest.raises(StagedArtifactUnavailableError):
        store.open_component(database_component)


def test_open_component_raises_integrity_error_on_digest_mismatch(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"original bytes"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    store.stage(digest, source_path)
    blob_path = store.root / "blobs" / f"sha256-{digest.value}.bin"
    blob_path.chmod(0o600)
    blob_path.write_bytes(b"corrupted bytes replacing the original payload")
    blob_path.chmod(0o600)
    manifest = _manifest_with(digest)
    database_component = manifest.components[0]

    with pytest.raises(StagedArtifactIntegrityError):
        store.open_component(database_component)


def test_resolve_raises_unavailable_for_unknown_ref(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")

    with pytest.raises(StagedArtifactUnavailableError):
        store.resolve(DataArtifactRef("never-put"))


def test_resolve_fails_closed_on_corrupt_manifest_json(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    manifest = _manifest_with(_digest_of(b"payload"))
    ref = DataArtifactRef(manifest.restore_set_id)
    store.put(ref, manifest)
    manifest_path = store.root / "manifests" / f"{ref}.json"
    manifest_path.chmod(0o600)
    manifest_path.write_text("{not valid json", encoding="utf-8")
    manifest_path.chmod(0o600)

    with pytest.raises(StagedArtifactStateError):
        store.resolve(ref)


def test_resolve_rejects_tampered_manifest_with_path_traversal_component_ref(
    tmp_path: Path,
) -> None:
    """A manifest file mutated on disk (outside Pydantic construction) with a
    traversal-shaped component ref MUST be rejected before any path is built
    from its fields (design threat matrix: "Store path derivation")."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    manifest = _manifest_with(_digest_of(b"payload"))
    ref = DataArtifactRef(manifest.restore_set_id)
    store.put(ref, manifest)
    manifest_path = store.root / "manifests" / f"{ref}.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["components"][0]["opaque_component_ref"] = "../../../etc/passwd"
    manifest_path.chmod(0o600)
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    manifest_path.chmod(0o600)

    with pytest.raises(StagedArtifactStateError):
        store.resolve(ref)


def test_blob_path_rejects_traversal_shaped_digest_defense_in_depth(tmp_path: Path) -> None:
    """Direct defense-in-depth: even a digest value bypassing `ArtifactDigest`'s own
    Pydantic validator (e.g. via `model_construct`) must never reach a path build."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    bypassed_digest = ArtifactDigest.model_construct(
        algorithm="sha256", value="../../../etc/passwd"
    )

    with pytest.raises(StagedArtifactCustodyError):
        store._blob_path(bypassed_digest)  # noqa: SLF001 - pinning a security boundary


def test_manifest_path_rejects_traversal_shaped_ref_defense_in_depth(tmp_path: Path) -> None:
    """Direct defense-in-depth mirror of the digest case, for the manifest ref."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")

    with pytest.raises(StagedArtifactCustodyError):
        store._manifest_path("../../../etc/passwd")  # noqa: SLF001 - pinning a security boundary


def test_discard_removes_manifest_and_blobs(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"discard me"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    manifest = _manifest_with(digest)
    ref = DataArtifactRef(manifest.restore_set_id)
    store.stage(digest, source_path)
    store.put(ref, manifest)

    outcome = store.discard(ref)

    assert outcome.code is DiscardOutcomeCode.COMPLETED
    assert not (store.root / "manifests" / f"{ref}.json").exists()
    assert not (store.root / "blobs" / f"sha256-{digest.value}.bin").exists()


def test_discard_is_idempotent_when_already_absent(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")

    outcome = store.discard(DataArtifactRef("never-existed"))

    assert outcome.code is DiscardOutcomeCode.COMPLETED


def test_open_component_accepts_uppercase_hex_digest_value(tmp_path: Path) -> None:
    """`_blob_path` always lowercases; the recomputed-vs-recorded digest
    comparison must normalize case too, or a byte-perfect blob whose recorded
    digest happens to be uppercase hex spuriously raises integrity failure."""
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"uppercase digest bytes"
    lowercase_digest = _digest_of(payload)
    uppercase_digest = ArtifactDigest(algorithm="sha256", value=lowercase_digest.value.upper())
    source_path = _write_source(tmp_path, "staged-dump", payload)
    store.stage(lowercase_digest, source_path)
    manifest = _manifest_with(uppercase_digest)
    database_component = manifest.components[0]

    opened_path = store.open_component(database_component)

    assert opened_path.read_bytes() == payload


def test_discard_preserves_blob_still_referenced_by_another_manifest(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"shared blob bytes"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    store.stage(digest, source_path)
    manifest_a = _manifest_with(digest, ref="restore-set-alpha")
    manifest_b = _manifest_with(digest, ref="restore-set-beta")
    ref_a = DataArtifactRef(manifest_a.restore_set_id)
    ref_b = DataArtifactRef(manifest_b.restore_set_id)
    store.put(ref_a, manifest_a)
    store.put(ref_b, manifest_b)

    outcome = store.discard(ref_a)

    assert outcome.code is DiscardOutcomeCode.COMPLETED
    assert not (store.root / "manifests" / f"{ref_a}.json").exists()
    resolved_b = store.resolve(ref_b)
    database_component_b = resolved_b.components[0]
    opened_path = store.open_component(database_component_b)
    assert opened_path.read_bytes() == payload


def test_discard_records_residual_on_genuine_unlink_failure_not_on_shared_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"failure blob bytes"
    digest = _digest_of(payload)
    source_path = _write_source(tmp_path, "staged-dump", payload)
    manifest = _manifest_with(digest)
    ref = DataArtifactRef(manifest.restore_set_id)
    store.stage(digest, source_path)
    store.put(ref, manifest)
    blob_path = store.root / "blobs" / f"sha256-{digest.value}.bin"
    original_unlink = Path.unlink

    def fake_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self == blob_path:
            raise OSError("simulated unlink failure")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    outcome = store.discard(ref)

    assert outcome.code is DiscardOutcomeCode.RESIDUAL_FAILURE
    assert "database-alpha" in outcome.residual_ids


def test_discard_on_corrupt_manifest_returns_outcome_without_raising(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    manifest = _manifest_with(_digest_of(b"payload"))
    ref = DataArtifactRef(manifest.restore_set_id)
    store.put(ref, manifest)
    manifest_path = store.root / "manifests" / f"{ref}.json"
    manifest_path.chmod(0o600)
    manifest_path.write_text("{not valid json", encoding="utf-8")
    manifest_path.chmod(0o600)

    outcome = store.discard(ref)

    assert outcome.code is DiscardOutcomeCode.COMPLETED
    assert not manifest_path.exists()


def test_hash_file_rejects_symlink_via_fd_custody(tmp_path: Path) -> None:
    """TOCTOU hardening: hashing must open with O_NOFOLLOW and re-check custody
    on the fd, not just lstat the path before opening it separately."""
    real_target = tmp_path / "outside-target.bin"
    real_target.write_bytes(b"toctou bytes")
    link_path = tmp_path / "link.bin"
    link_path.symlink_to(real_target)

    with pytest.raises(StagedArtifactCustodyError):
        FilesystemStagedArtifactStore._hash_file(link_path, "sha256")  # noqa: SLF001


def test_stage_rejects_symlinked_source_path(tmp_path: Path) -> None:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    payload = b"symlink source bytes"
    digest = _digest_of(payload)
    real_target = tmp_path / "outside-source.bin"
    real_target.write_bytes(payload)
    link_source = tmp_path / "link-source.bin"
    link_source.symlink_to(real_target)

    with pytest.raises(StagedArtifactCustodyError):
        store.stage(digest, link_source)

    assert real_target.exists()
    assert link_source.exists()
