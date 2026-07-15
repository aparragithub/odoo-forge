"""Pure published-artifact resolution values and failures."""

from dataclasses import dataclass

from odoo_forge.manifest.errors import ResolutionError


@dataclass(frozen=True)
class PublishedArtifactResolution:
    """A published artifact pinned to its declared version and immutable digest."""

    source: str
    version: str
    digest: str


class PublishedArtifactResolutionError(ResolutionError):
    def __init__(self, source: str, version: str, detail: str) -> None:
        self.source = source
        self.version = version
        self.detail = detail
        message = f"cannot resolve published artifact '{source}' at version '{version}': {detail}"
        super().__init__(message)


class PublishedArtifactNotFoundError(PublishedArtifactResolutionError):
    def __init__(self, source: str, version: str) -> None:
        super().__init__(source, version, "artifact not found")


class PublishedArtifactDigestMissingError(PublishedArtifactResolutionError):
    def __init__(self, source: str, version: str) -> None:
        super().__init__(source, version, "registry did not provide an immutable digest")


__all__ = [
    "PublishedArtifactResolution",
    "PublishedArtifactResolutionError",
    "PublishedArtifactNotFoundError",
    "PublishedArtifactDigestMissingError",
]
