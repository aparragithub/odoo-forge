from pathlib import Path

import pytest

from odoo_forge.project_catalog.interfaces import CatalogIndex
from odoo_forge.project_catalog.models import ProjectCatalogRequest
from odoo_forge_catalog import YamlCatalogIndex
from odoo_forge_catalog.errors import CatalogSourceError

_MATCHING_RECORD: dict[str, object] = {
    "record_id": "rec-acme",
    "client_key": "acme",
    "project_key": "acme-project",
    "manifest_ref": {"manifest_name": "acme", "manifest_path": "acme/project.yaml"},
}

_OTHER_RECORD: dict[str, object] = {
    "record_id": "rec-other",
    "client_key": "other",
    "project_key": "other-project",
}


def _write_catalog(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    import yaml

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(yaml.safe_dump({"records": records}))
    return catalog_path


def test_find_matches_returns_matching_record(tmp_path: Path) -> None:
    catalog_path = _write_catalog(tmp_path, [_MATCHING_RECORD, _OTHER_RECORD])
    index = YamlCatalogIndex(catalog_path)

    matches = index.find_matches(ProjectCatalogRequest(client_key="acme"))

    assert len(matches) == 1
    assert matches[0].record_id == "rec-acme"
    assert matches[0].client_key == "acme"


def test_find_matches_returns_empty_list_when_no_match(tmp_path: Path) -> None:
    catalog_path = _write_catalog(tmp_path, [_OTHER_RECORD])
    index = YamlCatalogIndex(catalog_path)

    matches = index.find_matches(ProjectCatalogRequest(client_key="acme"))

    assert matches == []


def test_find_matches_returns_all_ambiguous_matches(tmp_path: Path) -> None:
    duplicate_record = dict(_MATCHING_RECORD, record_id="rec-acme-2")
    catalog_path = _write_catalog(tmp_path, [_MATCHING_RECORD, duplicate_record])
    index = YamlCatalogIndex(catalog_path)

    matches = index.find_matches(ProjectCatalogRequest(client_key="acme"))

    assert len(matches) == 2
    assert {record.record_id for record in matches} == {"rec-acme", "rec-acme-2"}


def test_find_matches_raises_catalog_source_error_when_file_missing(tmp_path: Path) -> None:
    catalog_path = tmp_path / "does-not-exist.yaml"
    index = YamlCatalogIndex(catalog_path)

    with pytest.raises(CatalogSourceError):
        index.find_matches(ProjectCatalogRequest(client_key="acme"))


def test_find_matches_raises_catalog_source_error_on_malformed_yaml(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("records: [this is not: valid: yaml")
    index = YamlCatalogIndex(catalog_path)

    with pytest.raises(CatalogSourceError):
        index.find_matches(ProjectCatalogRequest(client_key="acme"))


def test_find_matches_raises_catalog_source_error_on_malformed_record_schema(
    tmp_path: Path,
) -> None:
    malformed_record: dict[str, object] = {
        "record_id": "rec-broken",
        "project_key": "broken-project",
    }
    catalog_path = _write_catalog(tmp_path, [malformed_record])
    index = YamlCatalogIndex(catalog_path)

    with pytest.raises(CatalogSourceError, match="rec-broken"):
        index.find_matches(ProjectCatalogRequest(client_key="acme"))


def test_yaml_catalog_index_is_structurally_a_catalog_index(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yaml"

    assert isinstance(YamlCatalogIndex(catalog_path), CatalogIndex)


def test_find_matches_by_project_slug_via_aliases(tmp_path: Path) -> None:
    """Test that find_matches can match records by project_slug stored in aliases."""
    record_with_aliases: dict[str, object] = {
        "record_id": "rec-acme",
        "client_key": "acme",
        "project_key": "acme-project",
        "aliases": {"project_slugs": ["slug-acme", "slug-acme-alt"]},
    }
    catalog_path = _write_catalog(tmp_path, [record_with_aliases, _OTHER_RECORD])
    index = YamlCatalogIndex(catalog_path)

    matches = index.find_matches(ProjectCatalogRequest(project_slug="slug-acme"))

    assert len(matches) == 1
    assert matches[0].record_id == "rec-acme"


def test_find_matches_by_manifest_name_via_aliases(tmp_path: Path) -> None:
    """Test that find_matches can match records by manifest_name stored in aliases."""
    record_with_aliases: dict[str, object] = {
        "record_id": "rec-acme",
        "client_key": "acme",
        "project_key": "acme-project",
        "aliases": {"manifest_names": ["manifest-acme", "manifest-acme-alt"]},
    }
    catalog_path = _write_catalog(tmp_path, [record_with_aliases, _OTHER_RECORD])
    index = YamlCatalogIndex(catalog_path)

    matches = index.find_matches(ProjectCatalogRequest(manifest_name="manifest-acme"))

    assert len(matches) == 1
    assert matches[0].record_id == "rec-acme"


def test_find_matches_raises_catalog_source_error_on_non_list_records(tmp_path: Path) -> None:
    """Test that non-list records value raises CatalogSourceError, not TypeError."""
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("records: 5")  # scalar, not a list
    index = YamlCatalogIndex(catalog_path)

    with pytest.raises(CatalogSourceError):
        index.find_matches(ProjectCatalogRequest(client_key="acme"))


def test_find_matches_raises_catalog_source_error_on_non_dict_top_level(tmp_path: Path) -> None:
    """Test that non-dict top-level YAML document raises CatalogSourceError."""
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("- item1\n- item2")  # list, not dict
    index = YamlCatalogIndex(catalog_path)

    with pytest.raises(CatalogSourceError):
        index.find_matches(ProjectCatalogRequest(client_key="acme"))
