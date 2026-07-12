"""Pure application service for authoritative project catalog resolution."""

import json

from odoo_forge.project_catalog.interfaces import CatalogIndex
from odoo_forge.project_catalog.models import (
    InvalidCatalogRecord,
    ProjectCatalogRequest,
    ProjectCatalogResolution,
    ProjectCatalogResolutionFailure,
    ResolvedCatalogResult,
    ValidatedCatalogRecord,
)
from odoo_forge.project_catalog.validation import validate_record


def _normalize(value: str | None) -> str | None:
    """Normalize one identifier, treating empty or whitespace-only input as absent."""
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def normalize_request(request: ProjectCatalogRequest) -> ProjectCatalogRequest:
    """Normalize identifiers before handing the request to catalog authority."""
    return ProjectCatalogRequest(
        client_key=_normalize(request.client_key),
        project_key=_normalize(request.project_key),
        project_slug=_normalize(request.project_slug),
        manifest_name=_normalize(request.manifest_name),
    )


def _request_fingerprint(request: ProjectCatalogRequest) -> str:
    return json.dumps(request.model_dump(exclude_none=True), sort_keys=True, separators=(",", ":"))


def _matched_by(request: ProjectCatalogRequest) -> str:
    return "+".join(request.supplied_dimensions())


class ProjectCatalogResolver:
    """Resolve exactly one valid catalog record without consumer-side fallback rules."""

    def __init__(self, catalog_index: CatalogIndex) -> None:
        self._catalog_index = catalog_index

    def resolve(self, request: ProjectCatalogRequest) -> ProjectCatalogResolution:
        normalized_request = normalize_request(request)
        fingerprint = _request_fingerprint(normalized_request)

        if not normalized_request.supplied_dimensions():
            # No usable identifier can select a catalog record, so catalog authority
            # is never consulted and no untraceable success is possible.
            return ProjectCatalogResolutionFailure(
                type="catalog-not-found",
                request_fingerprint=fingerprint,
                details={"identifiers": {}},
            )

        matches = self._catalog_index.find_matches(normalized_request)
        if not matches:
            return ProjectCatalogResolutionFailure(
                type="catalog-not-found",
                request_fingerprint=fingerprint,
                details={"identifiers": normalized_request.model_dump(exclude_none=True)},
            )
        if len(matches) > 1:
            return ProjectCatalogResolutionFailure(
                type="ambiguous-resolution",
                request_fingerprint=fingerprint,
                details={
                    "record_ids": [record.record_id for record in matches],
                    "matched_dimensions": list(normalized_request.supplied_dimensions()),
                },
            )

        validated = validate_record(matches[0])
        if isinstance(validated, InvalidCatalogRecord):
            return ProjectCatalogResolutionFailure(
                type="invalid-catalog",
                request_fingerprint=fingerprint,
                details=validated.model_dump(),
            )
        return _assemble(validated, _matched_by(normalized_request))


def _assemble(record: ValidatedCatalogRecord, matched_by: str) -> ResolvedCatalogResult:
    """Translate a validated authority record into fully resolved outputs."""
    return ResolvedCatalogResult(
        authority_record_id=record.record_id,
        matched_by=matched_by,
        manifest_ref=record.manifest_ref,
        source_context=record.source_context,
        data_policy_default=record.data_policy_default,
        target_default=record.target_default,
    )


__all__ = ["ProjectCatalogResolver", "normalize_request"]
