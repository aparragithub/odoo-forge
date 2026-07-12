"""Pure project catalog resolution domain."""

from odoo_forge.project_catalog.models import (
    CatalogAliases,
    CatalogDefaults,
    CatalogRecord,
    CatalogRepoRef,
    CatalogSourceContext,
    ManifestRef,
    ProjectCatalogRequest,
    ProjectCatalogResolutionFailure,
    ResolvedCatalogResult,
)
from odoo_forge.project_catalog.resolver import ProjectCatalogResolver

__all__ = [
    "CatalogAliases",
    "CatalogDefaults",
    "CatalogRecord",
    "CatalogRepoRef",
    "CatalogSourceContext",
    "ManifestRef",
    "ProjectCatalogRequest",
    "ProjectCatalogResolutionFailure",
    "ProjectCatalogResolver",
    "ResolvedCatalogResult",
]
