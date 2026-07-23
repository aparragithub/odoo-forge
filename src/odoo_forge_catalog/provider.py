"""Concrete `CatalogIndex` adapter reading a single declarative YAML file."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from odoo_forge.project_catalog.models import CatalogRecord, ProjectCatalogRequest
from odoo_forge_catalog.errors import CatalogSourceError


class YamlCatalogIndex:
    """Reads catalog records from a single ``catalog.yaml``-shaped file.

    No resolution, ambiguity handling, or defaulting logic lives here —
    every matching record is returned as-is; `ProjectCatalogResolver` owns
    tie-breaking and failure classification.
    """

    def __init__(self, catalog_path: Path = Path("catalog.yaml")) -> None:
        self._catalog_path = catalog_path

    def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]:
        records = self._load_records()
        supplied = request.supplied_dimensions()
        return [record for record in records if self._record_matches(record, request, supplied)]

    def _record_matches(
        self, record: CatalogRecord, request: ProjectCatalogRequest, supplied: tuple[str, ...]
    ) -> bool:
        """Check if a record matches all supplied dimensions.

        Handles both direct attributes (client_key, project_key) and
        alias-carried dimensions (project_slug, manifest_name).
        """
        for field in supplied:
            request_value = getattr(request, field)

            # Handle alias-carried dimensions
            if field == "project_slug":
                if request_value not in record.aliases.project_slugs:
                    return False
            elif field == "manifest_name":
                if request_value not in record.aliases.manifest_names:
                    return False
            else:
                # Direct attribute comparison
                if getattr(record, field) != request_value:
                    return False

        return True

    def _load_records(self) -> list[CatalogRecord]:
        try:
            text = self._catalog_path.read_text()
        except OSError as exc:
            raise CatalogSourceError(
                f"cannot read catalog file '{self._catalog_path}': {exc}"
            ) from exc

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise CatalogSourceError(
                f"malformed YAML in catalog file '{self._catalog_path}': {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise CatalogSourceError(
                f"invalid catalog file '{self._catalog_path}': top-level document must be "
                f"a mapping (dict), not {type(data).__name__}"
            )

        raw_records = data.get("records", [])

        if not isinstance(raw_records, list):
            raise CatalogSourceError(
                f"invalid catalog file '{self._catalog_path}': 'records' must be a list, "
                f"not {type(raw_records).__name__}"
            )

        records: list[CatalogRecord] = []
        for index, raw_record in enumerate(raw_records):
            try:
                records.append(CatalogRecord.model_validate(raw_record))
            except ValidationError as exc:
                record_id = raw_record.get("record_id") if isinstance(raw_record, dict) else None
                identifier = record_id if record_id is not None else f"index {index}"
                raise CatalogSourceError(
                    f"malformed catalog record '{identifier}' in '{self._catalog_path}': {exc}"
                ) from exc
        return records


__all__ = ["YamlCatalogIndex"]
