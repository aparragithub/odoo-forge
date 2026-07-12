from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.project_catalog.models import (
    IDENTIFIER_DIMENSIONS,
    CatalogDefaults,
    CatalogRecord,
    CatalogRepoRef,
    CatalogSourceContext,
    InvalidCatalogRecord,
    ManifestRef,
    ProjectCatalogRequest,
    ProjectCatalogResolutionFailure,
    ResolvedCatalogResult,
    ValidatedCatalogRecord,
)
from odoo_forge.project_catalog.resolver import ProjectCatalogResolver
from odoo_forge.project_catalog.validation import validate_record


class _CatalogIndex:
    def __init__(self, records: list[CatalogRecord]) -> None:
        self._records = records

    def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]:
        del request
        return self._records


def _record() -> CatalogRecord:
    return CatalogRecord(
        record_id="acme-website",
        client_key="acme",
        project_key="website",
        manifest_ref=ManifestRef(manifest_name="acme-website", manifest_path="catalog/acme.yaml"),
        source_context=CatalogSourceContext(
            source_set_id="acme-website-sources",
            repos=[
                CatalogRepoRef(
                    url="https://github.com/acme/website.git",
                    ref="v1.2.3",
                    role="application",
                )
            ],
        ),
        defaults=CatalogDefaults(data_policy="masked-copy", target="staging"),
    )


def test_resolves_one_catalog_record_to_full_authoritative_result() -> None:
    resolver = ProjectCatalogResolver(_CatalogIndex([_record()]))

    result = resolver.resolve(ProjectCatalogRequest(client_key=" ACME ", project_key="Website"))

    assert isinstance(result, ResolvedCatalogResult)
    assert result.authority_record_id == "acme-website"
    assert result.matched_by == "client_key+project_key"
    assert result.manifest_ref.manifest_path == "catalog/acme.yaml"
    assert result.source_context.source_set_id == "acme-website-sources"
    assert result.data_policy_default == "masked-copy"
    assert result.target_default == "staging"


def test_returns_not_found_for_zero_catalog_matches() -> None:
    result = ProjectCatalogResolver(_CatalogIndex([])).resolve(
        ProjectCatalogRequest(client_key="acme", project_key="missing")
    )

    assert isinstance(result, ProjectCatalogResolutionFailure)
    assert result.type == "catalog-not-found"
    assert result.details == {"identifiers": {"client_key": "acme", "project_key": "missing"}}


def test_returns_ambiguous_resolution_without_tie_breaking() -> None:
    first = _record()
    second = _record().model_copy(update={"record_id": "acme-website-copy"})

    result = ProjectCatalogResolver(_CatalogIndex([first, second])).resolve(
        ProjectCatalogRequest(client_key="acme", project_key="website")
    )

    assert isinstance(result, ProjectCatalogResolutionFailure)
    assert result.type == "ambiguous-resolution"
    assert result.details["record_ids"] == ["acme-website", "acme-website-copy"]


def test_ambiguous_resolution_reports_matched_identifier_dimensions() -> None:
    first = _record()
    second = _record().model_copy(update={"record_id": "acme-website-copy"})

    result = ProjectCatalogResolver(_CatalogIndex([first, second])).resolve(
        ProjectCatalogRequest(manifest_name="acme-website", client_key="acme")
    )

    assert isinstance(result, ProjectCatalogResolutionFailure)
    assert result.details == {
        "record_ids": ["acme-website", "acme-website-copy"],
        "matched_dimensions": ["client_key", "manifest_name"],
    }


def test_returns_invalid_catalog_when_selected_record_has_missing_outputs() -> None:
    incomplete = _record().model_copy(
        update={"manifest_ref": None, "defaults": CatalogDefaults(data_policy="masked-copy")}
    )

    result = ProjectCatalogResolver(_CatalogIndex([incomplete])).resolve(
        ProjectCatalogRequest(client_key="acme", project_key="website")
    )

    assert isinstance(result, ProjectCatalogResolutionFailure)
    assert result.type == "invalid-catalog"
    assert result.details == {
        "record_id": "acme-website",
        "invalid_fields": ["manifest_ref", "target_default"],
        "reason_code": "missing:manifest_ref+target_default",
    }


def _resolve_incomplete(**update: object) -> ProjectCatalogResolutionFailure:
    incomplete = _record().model_copy(update=update)
    result = ProjectCatalogResolver(_CatalogIndex([incomplete])).resolve(
        ProjectCatalogRequest(client_key="acme", project_key="website")
    )
    assert isinstance(result, ProjectCatalogResolutionFailure)
    return result


def test_returns_invalid_catalog_when_only_manifest_ref_is_missing() -> None:
    result = _resolve_incomplete(manifest_ref=None)

    assert result.type == "invalid-catalog"
    assert result.details == {
        "record_id": "acme-website",
        "invalid_fields": ["manifest_ref"],
        "reason_code": "missing:manifest_ref",
    }


def test_returns_invalid_catalog_when_only_source_context_is_missing() -> None:
    result = _resolve_incomplete(source_context=None)

    assert result.type == "invalid-catalog"
    assert result.details == {
        "record_id": "acme-website",
        "invalid_fields": ["source_context"],
        "reason_code": "missing:source_context",
    }


def test_returns_invalid_catalog_when_only_data_policy_default_is_missing() -> None:
    result = _resolve_incomplete(defaults=CatalogDefaults(target="staging"))

    assert result.type == "invalid-catalog"
    assert result.details == {
        "record_id": "acme-website",
        "invalid_fields": ["data_policy_default"],
        "reason_code": "missing:data_policy_default",
    }


def test_returns_invalid_catalog_when_only_target_default_is_missing() -> None:
    result = _resolve_incomplete(defaults=CatalogDefaults(data_policy="masked-copy"))

    assert result.type == "invalid-catalog"
    assert result.details == {
        "record_id": "acme-website",
        "invalid_fields": ["target_default"],
        "reason_code": "missing:target_default",
    }


def test_invalid_catalog_reason_code_is_deterministic_across_resolutions() -> None:
    first = _resolve_incomplete(manifest_ref=None, source_context=None)
    second = _resolve_incomplete(source_context=None, manifest_ref=None)

    assert first.details["reason_code"] == "missing:manifest_ref+source_context"
    assert first.details["reason_code"] == second.details["reason_code"]


def test_validated_catalog_record_cannot_represent_missing_required_outputs() -> None:
    with pytest.raises(ValidationError):
        cast(Any, ValidatedCatalogRecord)(record_id="acme-website")


def test_validate_record_returns_a_validated_record_for_a_complete_record() -> None:
    validated = validate_record(_record())

    assert isinstance(validated, ValidatedCatalogRecord)
    assert validated.record_id == "acme-website"
    assert validated.data_policy_default == "masked-copy"
    assert validated.target_default == "staging"


def test_validate_record_returns_an_invalid_record_for_an_incomplete_record() -> None:
    invalid = validate_record(_record().model_copy(update={"source_context": None}))

    assert isinstance(invalid, InvalidCatalogRecord)
    assert invalid.invalid_fields == ["source_context"]
    assert invalid.reason_code == "missing:source_context"


def test_request_field_order_matches_declared_identifier_dimensions() -> None:
    assert tuple(ProjectCatalogRequest.model_fields) == IDENTIFIER_DIMENSIONS


def test_matched_by_follows_declared_dimension_order_not_construction_order() -> None:
    resolver = ProjectCatalogResolver(_CatalogIndex([_record()]))

    result = resolver.resolve(
        ProjectCatalogRequest(manifest_name="acme-website", client_key="acme")
    )

    assert isinstance(result, ResolvedCatalogResult)
    assert result.matched_by == "client_key+manifest_name"


def test_supplied_dimensions_are_derived_from_declared_dimension_order() -> None:
    request = ProjectCatalogRequest(project_slug="website", client_key="acme")

    assert request.supplied_dimensions() == ("client_key", "project_slug")


class _CapturingIndex:
    def __init__(self, records: list[CatalogRecord]) -> None:
        self._records = records
        self.received_request: ProjectCatalogRequest | None = None

    def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]:
        self.received_request = request
        return self._records


def test_normalizes_identifiers_before_catalog_lookup() -> None:
    index = _CapturingIndex([_record()])
    request = ProjectCatalogRequest(client_key=" ACME ", project_key="Website")
    ProjectCatalogResolver(index).resolve(request)

    assert index.received_request == ProjectCatalogRequest(client_key="acme", project_key="website")


def test_treats_empty_and_whitespace_identifiers_as_absent_for_lookup() -> None:
    index = _CapturingIndex([_record()])
    request = ProjectCatalogRequest(client_key="acme", project_slug="   ", manifest_name="")

    result = ProjectCatalogResolver(index).resolve(request)

    assert index.received_request == ProjectCatalogRequest(client_key="acme")
    assert isinstance(result, ResolvedCatalogResult)
    assert result.matched_by == "client_key"


def test_blank_identifiers_are_omitted_from_fingerprint_and_failure_details() -> None:
    result = ProjectCatalogResolver(_CatalogIndex([])).resolve(
        ProjectCatalogRequest(client_key="acme", project_key="  ", project_slug="")
    )

    assert isinstance(result, ProjectCatalogResolutionFailure)
    assert result.request_fingerprint == '{"client_key":"acme"}'
    assert result.details == {"identifiers": {"client_key": "acme"}}


def test_request_without_any_usable_identifier_is_not_found_without_consulting_catalog() -> None:
    index = _CapturingIndex([_record()])

    result = ProjectCatalogResolver(index).resolve(ProjectCatalogRequest(client_key="   "))

    assert index.received_request is None
    assert isinstance(result, ProjectCatalogResolutionFailure)
    assert result.type == "catalog-not-found"
    assert result.request_fingerprint == "{}"
    assert result.details == {"identifiers": {}}
