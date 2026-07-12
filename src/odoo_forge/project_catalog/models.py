"""Typed, declarative models for project catalog resolution."""

from typing import Literal

from pydantic import BaseModel, Field


class ProjectCatalogRequest(BaseModel):
    client_key: str | None = None
    project_key: str | None = None
    project_slug: str | None = None
    manifest_name: str | None = None


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
    "CatalogAliases",
    "CatalogDefaults",
    "CatalogRecord",
    "CatalogRepoRef",
    "CatalogSourceContext",
    "ManifestRef",
    "ProjectCatalogRequest",
    "ProjectCatalogResolution",
    "ProjectCatalogResolutionFailure",
    "ResolvedCatalogResult",
]
