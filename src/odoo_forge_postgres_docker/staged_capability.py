"""Store-backed `DataArtifactCapability` and `RestoreByteSource` (design D10, bridge slice B2).

`StagedArtifactCapability` is the concrete `DataArtifactCapability`
(`odoo_forge.data_artifacts.contracts.DataArtifactCapability`) backed by a
`StagedArtifactStore` (bridge slice B1): `resolve` reads the store's manifest,
`validate_for_restore` re-verifies every component's staged bytes against
their recorded digest (mapping the store's typed failures to the correct
`ValidationFailureCode`), and `discard` delegates to the store.

`make_staged_byte_source` builds a `RestoreByteSource`
(`odoo_forge_postgres_docker.restore_target.RestoreByteSource`) that resolves
a `RestoreSetComponent` to its staged, digest-verified file via the same
store, so it can be injected into `make_docker_restore_target`.

Neither is wired into capture, the coordinator, composition, or the CLI in
this slice (that is bridge slices B3-B5).
"""

from __future__ import annotations

from pathlib import Path

from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    DataArtifactCapability,
    DiscardOutcome,
    RestoreReadiness,
    RestoreSetComponent,
    RestoreSetManifest,
    ValidationFailureCode,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge_postgres_docker.restore_target import RestoreByteSource
from odoo_forge_postgres_docker.staged_store import (
    StagedArtifactCustodyError,
    StagedArtifactIntegrityError,
    StagedArtifactStateError,
    StagedArtifactUnavailableError,
)


class StagedArtifactCapability:
    """`DataArtifactCapability` backed by a `StagedArtifactStore` (design D10).

    Structurally satisfies
    `odoo_forge.data_artifacts.contracts.DataArtifactCapability`.
    """

    def __init__(self, store: StagedArtifactStore) -> None:
        self._store = store

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        return self._store.resolve(ref)

    def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness:
        """Re-verify the staged database component's bytes against its recorded digest.

        A missing or corrupt manifest, or a missing/inaccessible database
        blob, maps to `ValidationFailureCode.UNAVAILABLE`; a database blob
        whose recomputed digest does not match its recorded digest maps to
        `ValidationFailureCode.INTEGRITY_FAILED` — verified against the REAL
        staged bytes, not a stored scalar. The `filestore` component is
        metadata-only (design D6/D8: its restore is a no-op pass-through, so
        it never has staged bytes to verify).
        """
        try:
            manifest = self._store.resolve(ref)
        except (StagedArtifactUnavailableError, StagedArtifactStateError):
            return RestoreReadiness(
                ready=False,
                manifest=None,
                failure_code=ValidationFailureCode.UNAVAILABLE,
                redacted_detail=None,
            )
        database_components = (
            component
            for component in manifest.components
            if component.kind is ArtifactComponentKind.DATABASE
        )
        for component in database_components:
            try:
                self._store.open_component(component)
            except StagedArtifactIntegrityError:
                return RestoreReadiness(
                    ready=False,
                    manifest=None,
                    failure_code=ValidationFailureCode.INTEGRITY_FAILED,
                    redacted_detail=None,
                )
            except (StagedArtifactUnavailableError, StagedArtifactCustodyError):
                return RestoreReadiness(
                    ready=False,
                    manifest=None,
                    failure_code=ValidationFailureCode.UNAVAILABLE,
                    redacted_detail=None,
                )
        return RestoreReadiness(
            ready=True, manifest=manifest, failure_code=None, redacted_detail=None
        )

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        return self._store.discard(ref)


def make_staged_byte_source(store: StagedArtifactStore) -> RestoreByteSource:
    """Build a `RestoreByteSource` resolving a component's bytes via `store`.

    `store.open_component` verifies the recomputed digest against the
    component's recorded digest, so an injected caller (e.g.
    `make_docker_restore_target(byte_source=...)`) never streams
    digest-mismatched or missing bytes.
    """

    def _byte_source(component: RestoreSetComponent) -> Path:
        return store.open_component(component)

    return _byte_source


__all__ = ["StagedArtifactCapability", "make_staged_byte_source"]

# Compile-time structural check (mirrors other adapter modules' convention):
# `StagedArtifactCapability` must structurally satisfy the runtime-checkable
# `DataArtifactCapability` protocol.
_: type[DataArtifactCapability] = StagedArtifactCapability
