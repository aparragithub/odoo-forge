from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryError,
    RegistryImageNotFoundError,
    RegistryPublishError,
    RegistryPullError,
    RegistryUnavailableError,
    UnsupportedRegistryError,
)
from odoo_forge.image_registry.reference import (
    normalize_digest_image_reference,
    normalize_image_reference,
    normalize_publishable_image_reference,
)
from odoo_forge.image_registry.types import ImageDigestRef, ImageRef, LocalImageRef

__all__ = [
    "RegistryError",
    "UnsupportedRegistryError",
    "MalformedImageReferenceError",
    "RegistryPublishError",
    "RegistryPullError",
    "RegistryAuthenticationError",
    "RegistryImageNotFoundError",
    "RegistryUnavailableError",
    "ImageRef",
    "ImageDigestRef",
    "LocalImageRef",
    "normalize_image_reference",
    "normalize_publishable_image_reference",
    "normalize_digest_image_reference",
]
