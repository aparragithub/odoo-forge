from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryError,
    RegistryImageNotFoundError,
    RegistryUnavailableError,
    UnsupportedRegistryError,
)
from odoo_forge.image_registry.reference import normalize_image_reference

__all__ = [
    "RegistryError",
    "UnsupportedRegistryError",
    "MalformedImageReferenceError",
    "RegistryAuthenticationError",
    "RegistryImageNotFoundError",
    "RegistryUnavailableError",
    "normalize_image_reference",
]
