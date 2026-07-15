"""Pure-core published artifact resolution contract."""

from typing import Protocol, runtime_checkable

from odoo_forge.manifest.artifacts import PublishedArtifactResolution


@runtime_checkable
class PublishedArtifactResolver(Protocol):
    def resolve(self, source: str, version: str) -> PublishedArtifactResolution:
        """Resolve a declared source/version pair to an immutable artifact digest."""
        ...


__all__ = ["PublishedArtifactResolver"]
