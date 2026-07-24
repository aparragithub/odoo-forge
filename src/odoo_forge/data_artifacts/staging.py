"""Pure-domain port for content-addressed staging custody of captured artifact bytes.

`StagedArtifactStore` is the durable, filesystem-backed boundary that owns
captured bytes for the life of one copy operation (design D7/D8, bridge
slice B1 of `sdd/wf-data-copy`). It is kept separate from
`DataArtifactCapability`: THIS port persists staged bytes and their manifest
under a content-addressed key; `DataArtifactCapability` (a later bridge
slice) resolves/validates/discards a restore set BY REFERENCE, backed by a
concrete `StagedArtifactStore` implementation.

Only the port lives here; `FilesystemStagedArtifactStore`
(`odoo_forge_postgres_docker/staged_store.py`) is the sole concrete
implementation in this slice. No capture/restore/coordinator wiring happens
here (that is bridge slices B2-B5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from odoo_forge.data_artifacts.contracts import (
    ArtifactDigest,
    DiscardOutcome,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.types import DataArtifactRef


@runtime_checkable
class StagedArtifactStore(Protocol):
    """Content-addressed custody for staged artifact bytes and their manifest."""

    def stage(self, digest: ArtifactDigest, source_path: Path) -> None:
        """Move `source_path`'s bytes into custody, keyed by `digest`.

        Content-addressed: staging the same `digest` twice is a dedup no-op.
        """
        ...

    def put(self, ref: DataArtifactRef, manifest: RestoreSetManifest) -> None:
        """Persist `manifest` under `ref`, superseding any prior record for `ref`."""
        ...

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        """Return the manifest persisted under `ref`, failing closed if absent or corrupt."""
        ...

    def open_component(self, component: RestoreSetComponent) -> Path:
        """Return a readable path to `component`'s staged bytes, verifying its digest.

        Raises a typed error if the blob is absent or its recomputed digest
        does not match `component.digest`.
        """
        ...

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        """Remove `ref`'s manifest and its staged blobs; idempotent when already absent."""
        ...


__all__ = ["StagedArtifactStore"]
