"""Registry adapter for manifest ``registry://`` published artifacts."""

import re
from typing import Protocol

from odoo_forge.image_registry.errors import RegistryError, RegistryImageNotFoundError
from odoo_forge.image_registry.types import ImageDigestRef, ImageRef
from odoo_forge.manifest.artifacts import (
    PublishedArtifactDigestMissingError,
    PublishedArtifactNotFoundError,
    PublishedArtifactResolution,
    PublishedArtifactResolutionError,
)


class RegistryDigestResolver(Protocol):
    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef:
        """Resolve a tag reference to an immutable digest reference."""
        ...


class PublishedArtifactRegistryResolver:
    """Translate manifest registry declarations through the image registry port."""

    def __init__(self, registry: RegistryDigestResolver) -> None:
        self._registry = registry

    def resolve(self, source: str, version: str) -> PublishedArtifactResolution:
        ref = _registry_reference(source, version)
        try:
            resolved = str(self._registry.resolve_digest(ImageRef(ref)))
        except RegistryImageNotFoundError as exc:
            raise PublishedArtifactNotFoundError(source, version) from exc
        except RegistryError as exc:
            raise PublishedArtifactResolutionError(source, version, str(exc)) from exc

        _, separator, digest = resolved.partition("@")
        if separator != "@" or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise PublishedArtifactDigestMissingError(source, version)
        return PublishedArtifactResolution(source=source, version=version, digest=digest)


def _registry_reference(source: str, version: str) -> str:
    path = source.removeprefix("registry://")
    if path == source or not path:
        raise PublishedArtifactResolutionError(source, version, "source must use registry://<path>")
    return f"ghcr.io/{path}:{version}"


__all__ = ["PublishedArtifactRegistryResolver", "RegistryDigestResolver"]
