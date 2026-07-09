"""Immutable image-registry contract port.

`odoo_forge` depends only on this structural interface. Concrete registry
adapters live outside the core package and MUST NOT be imported here.
"""

from typing import Protocol, runtime_checkable

from odoo_forge.image_registry.types import ImageDigestRef, ImageRef, LocalImageRef


@runtime_checkable
class ImageRegistryProvider(Protocol):
    def publish(self, ref: ImageRef) -> ImageDigestRef:
        """Publish a built local image and return its immutable digest ref."""
        ...

    def pull(self, digest: ImageDigestRef) -> LocalImageRef:
        """Prefetch a digest into the local daemon and return a local handle."""
        ...

    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef:
        """Resolve `ref` to a canonical immutable digest reference."""
        ...

    def exists(self, digest: ImageDigestRef) -> bool:
        """Check whether `digest` exists remotely without transferring layers."""
        ...


__all__ = ["ImageRegistryProvider"]
