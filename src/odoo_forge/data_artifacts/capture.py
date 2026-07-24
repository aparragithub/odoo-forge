"""Pure-domain port for producing a digest-verified restore set from a LIVE source.

`CaptureSource` is a distinct opaque type from the delivery-side `TargetContext`
used by `DataArtifactCapability`/`DatabaseProvider.restore()`. It composes an
opaque `CredentialHandle` (materialized exclusively through the existing
`materialize_for_target`, which already accepts `TargetContext(kind="source")`)
with `TargetContext(kind="source")` — the LIVE source's OWN trust boundary.

This is never `TargetContext(kind="database")`: that value represents the
DELIVERY target consumed by `DatabaseProvider.restore()`. Reconciliation note
(tasks 0.1): the spec's "never TargetContext" wording means capture must never
carry a delivery-target context, not that it avoids `TargetContext` entirely —
`CaptureSource` reuses `TargetContext` with the distinct `"source"` kind that
already exists in the credentials type vocabulary.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import model_validator

from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.contracts import RestoreSetManifest
from odoo_forge.data_artifacts.types import _ArtifactValue


class CaptureSource(_ArtifactValue):
    credentials: CredentialHandle
    target: TargetContext

    @model_validator(mode="after")
    def require_source_target_kind(self) -> CaptureSource:
        if self.target.kind != "source":
            raise ValueError("capture source target must be kind='source'")
        return self


@runtime_checkable
class DataArtifactCaptureCapability(Protocol):
    def capture(self, source: CaptureSource) -> RestoreSetManifest: ...


__all__ = ["CaptureSource", "DataArtifactCaptureCapability"]
