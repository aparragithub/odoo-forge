from odoo_forge.project_catalog.interfaces import CatalogIndex
from odoo_forge_cli import _composition


def test_make_catalog_index_returns_protocol_conforming_instance() -> None:
    result = _composition._make_catalog_index()

    assert isinstance(result, CatalogIndex)
