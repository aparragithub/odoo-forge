"""Structural contract tests for the `StagedArtifactStore` port."""

from pathlib import Path

from odoo_forge.data_artifacts.contracts import (
    ArtifactDigest,
    DiscardOutcome,
    DiscardOutcomeCode,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.data_artifacts.types import DataArtifactRef


class _FakeStagedArtifactStore:
    """Minimal structural fake proving `StagedArtifactStore` is a satisfiable Protocol."""

    def stage(self, digest: ArtifactDigest, source_path: Path) -> None:
        return None

    def put(self, ref: DataArtifactRef, manifest: RestoreSetManifest) -> None:
        return None

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        raise NotImplementedError

    def open_component(self, component: RestoreSetComponent) -> Path:
        raise NotImplementedError

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        return DiscardOutcome(code=DiscardOutcomeCode.COMPLETED)


def test_fake_store_satisfies_the_protocol_structurally() -> None:
    store: StagedArtifactStore = _FakeStagedArtifactStore()

    assert isinstance(store, StagedArtifactStore)
