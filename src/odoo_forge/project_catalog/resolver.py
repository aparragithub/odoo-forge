"""Pure application service for authoritative project catalog resolution."""

import json

from odoo_forge.project_catalog.interfaces import CatalogIndex
from odoo_forge.project_catalog.models import (
    CatalogRecord,
    ProjectCatalogRequest,
    ProjectCatalogResolution,
    ProjectCatalogResolutionFailure,
    ResolvedCatalogResult,
)
from odoo_forge.project_catalog.validation import invalid_required_fields


def _normalize(value: str | None) -> str | None:
    return value.strip().lower() if value is not None else None


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
    dimensions = [
        name
        for name, value in request.model_dump().items()
        if value is not None
    ]
    return "+".join(dimensions)


class ProjectCatalogResolver:
    """Resolve exactly one valid catalog record without consumer-side fallback rules."""

    def __init__(self, catalog_index: CatalogIndex) -> None:
        self._catalog_index = catalog_index

    def resolve(self, request: ProjectCatalogRequest) -> ProjectCatalogResolution:
        normalized_request = normalize_request(request)
        matches = self._catalog_index.find_matches(normalized_request)
        fingerprint = _request_fingerprint(normalized_request)

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
                details={"record_ids": [record.record_id for record in matches]},
            )

        record = matches[0]
        invalid_fields = invalid_required_fields(record)
        if invalid_fields:
            return ProjectCatalogResolutionFailure(
                type="invalid-catalog",
                request_fingerprint=fingerprint,
                details={"record_id": record.record_id, "invalid_fields": invalid_fields},
            )
        return _assemble(record, _matched_by(normalized_request))


def _assemble(record: CatalogRecord, matched_by: str) -> ResolvedCatalogResult:
    """Translate a validated authority record into fully resolved outputs."""
    assert record.manifest_ref is not None
    assert record.source_context is not None
    assert record.defaults.data_policy is not None
    assert record.defaults.target is not None
    return ResolvedCatalogResult(
        authority_record_id=record.record_id,
        matched_by=matched_by,
        manifest_ref=record.manifest_ref,
        source_context=record.source_context,
        data_policy_default=record.defaults.data_policy,
        target_default=record.defaults.target,
    )


__all__ = ["ProjectCatalogResolver", "normalize_request"]
