"""Public contract for approved provider adapter catalog resolution."""

from odoo_forge.provider_catalog.models import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderCatalogFailureCode,
    ProviderCatalogResolution,
    ProviderCatalogResolutionFailure,
    ProviderKind,
    ResolvedProviderAdapter,
)
from odoo_forge.provider_catalog.resolver import ProviderCatalogResolver

__all__ = [
    "ApprovedProviderAdapter",
    "GlobalProviderBinding",
    "ProviderCatalog",
    "ProviderCatalogFailureCode",
    "ProviderCatalogResolution",
    "ProviderCatalogResolutionFailure",
    "ProviderCatalogResolver",
    "ProviderKind",
    "ResolvedProviderAdapter",
]
