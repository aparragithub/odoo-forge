"""Typed, declarative models for project catalog resolution."""

from typing import Literal

from pydantic import BaseModel, Field

IDENTIFIER_DIMENSIONS: tuple[str, ...] = (
    "client_key",
    "project_key",
    "project_slug",
    "manifest_name",
)
"""Canonical, ordered identifier dimensions accepted by catalog lookup.

This ordering is the public contract behind `matched_by`; it never depends on
the field-declaration order of `ProjectCatalogRequest`.
"""


class ProjectCatalogRequest(BaseModel):
    client_key: str | None = None
    project_key: str | None = None
    project_slug: str | None = None
    manifest_name: str | None = None

    def supplied_dimensions(self) -> tuple[str, ...]:
        """Return the supplied identifier dimensions in canonical order."""
        return tuple(name for name in IDENTIFIER_DIMENSIONS if getattr(self, name) is not None)


class CatalogAliases(BaseModel):
    project_slugs: list[str] = Field(default_factory=list)
    manifest_names: list[str] = Field(default_factory=list)


class ManifestRef(BaseModel):
    manifest_name: str
    manifest_path: str


class CatalogRepoRef(BaseModel):
    url: str
    ref: str
    role: str


class CatalogSourceContext(BaseModel):
    source_set_id: str
    repos: list[CatalogRepoRef]


class CatalogDefaults(BaseModel):
    data_policy: str | None = None
    target: str | None = None


class CatalogRecord(BaseModel):
    record_id: str
    client_key: str
    project_key: str
    aliases: CatalogAliases = Field(default_factory=CatalogAliases)
    manifest_ref: ManifestRef | None = None
    source_context: CatalogSourceContext | None = None
    defaults: CatalogDefaults = Field(default_factory=CatalogDefaults)


class ValidatedCatalogRecord(BaseModel):
    """A catalog record proven to carry every required resolution output."""

    record_id: str
    manifest_ref: ManifestRef
    source_context: CatalogSourceContext
    data_policy_default: str
    target_default: str


class InvalidCatalogRecord(BaseModel):
    """A catalog record that cannot produce a resolution, with its failure classification."""

    record_id: str
    invalid_fields: list[str]
    reason_code: str


class ResolvedCatalogResult(BaseModel):
    authority_record_id: str
    matched_by: str
    manifest_ref: ManifestRef
    source_context: CatalogSourceContext
    data_policy_default: str
    target_default: str


class ProjectCatalogResolutionFailure(BaseModel):
    type: Literal["ambiguous-resolution", "catalog-not-found", "invalid-catalog"]
    request_fingerprint: str
    details: dict[str, object]


ProjectCatalogResolution = ResolvedCatalogResult | ProjectCatalogResolutionFailure


__all__ = [
    "IDENTIFIER_DIMENSIONS",
    "CatalogAliases",
    "CatalogDefaults",
    "CatalogRecord",
    "CatalogRepoRef",
    "CatalogSourceContext",
    "InvalidCatalogRecord",
    "ManifestRef",
    "ProjectCatalogRequest",
    "ProjectCatalogResolution",
    "ProjectCatalogResolutionFailure",
    "ResolvedCatalogResult",
    "ValidatedCatalogRecord",
]
