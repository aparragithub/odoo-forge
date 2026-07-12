"""Read-only ports for catalog authority."""

from typing import Protocol

from odoo_forge.project_catalog.models import CatalogRecord, ProjectCatalogRequest


class CatalogIndex(Protocol):
    def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]:
        """Return every catalog record matching the normalized request."""
        ...


__all__ = ["CatalogIndex"]
