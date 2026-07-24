"""RED-first tests for the DataArtifactCaptureCapability port contract shape."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource, DataArtifactCaptureCapability
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
    RestoreSetManifest,
)

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class _FakeCaptureCapability:
    """Minimal in-memory capability proving the port's contract shape."""

    def capture(self, source: CaptureSource) -> RestoreSetManifest:
        payload = b"pg_dump-bytes-for-" + source.target.target_id.encode()
        digest = ArtifactDigest(algorithm="sha256", value=hashlib.sha256(payload).hexdigest())
        return RestoreSetManifest(
            restore_set_id="restore-set-1",
            lineage_id="lineage-1",
            components=(
                RestoreSetComponent(
                    kind=ArtifactComponentKind.DATABASE,
                    opaque_component_ref="database-component-1",
                    format_version="v1",
                    digest=digest,
                ),
                RestoreSetComponent(
                    kind=ArtifactComponentKind.FILESTORE,
                    opaque_component_ref="filestore-component-1",
                    format_version="empty-v1",
                    digest=ArtifactDigest(algorithm="sha256", value=_EMPTY_SHA256),
                ),
            ),
        )


def _source() -> CaptureSource:
    return CaptureSource(
        credentials=CredentialHandle("source-handle"),
        target=TargetContext(kind="source", target_id="live-source"),
    )


def test_capture_source_requires_source_target_kind() -> None:
    with pytest.raises(ValidationError):
        CaptureSource(
            credentials=CredentialHandle("source-handle"),
            target=TargetContext(kind="database", target_id="delivery-target"),
        )


def test_capture_source_accepts_source_target_kind() -> None:
    source = _source()
    assert source.target.kind == "source"


def test_capability_protocol_accepts_conforming_capture() -> None:
    assert isinstance(_FakeCaptureCapability(), DataArtifactCaptureCapability)


def test_capture_returns_manifest_with_db_and_empty_filestore_digest_precomputed() -> None:
    manifest = _FakeCaptureCapability().capture(_source())

    kinds = {component.kind for component in manifest.components}
    assert kinds == {ArtifactComponentKind.DATABASE, ArtifactComponentKind.FILESTORE}

    filestore = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.FILESTORE
    )
    assert filestore.format_version == "empty-v1"
    assert filestore.digest.value == _EMPTY_SHA256

    database = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert len(database.digest.value) == 64
    assert database.digest.algorithm == "sha256"
