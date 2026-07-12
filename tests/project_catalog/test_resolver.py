from odoo_forge.project_catalog.models import (
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
    }


def test_normalizes_identifiers_before_catalog_lookup() -> None:
    class _CapturingIndex:
        received_request: ProjectCatalogRequest | None = None

        def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]:
            self.received_request = request
            return [_record()]

    index = _CapturingIndex()
    request = ProjectCatalogRequest(client_key=" ACME ", project_key="Website")
    ProjectCatalogResolver(index).resolve(request)

    assert index.received_request == ProjectCatalogRequest(client_key="acme", project_key="website")
