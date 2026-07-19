"""Pure Pydantic v2 schema for `project.yaml` — the manifest domain.

No git/docker/network access. Every model here describes intent only;
resolution (SHAs, branch names) happens during composition/materialization
in later slices.
"""

import ipaddress
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_REQUIRES_EDITION_MIGRATION_ERROR = (
    "'requires_edition' has been removed. Use the top-level 'enterprise:' block "
    "to declare the enterprise source, and 'requires_enterprise: true' on a "
    "layer to declare it needs enterprise present as a precondition."
)


class _LegacyEditionKeyRejector(BaseModel):
    """Base mixin for models that could carry the removed `requires_edition`
    key. Rejects it with an actionable migration error instead of the generic
    `extra="forbid"` message. Subclasses opt into `extra="forbid"` themselves."""

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_requires_edition(cls, data: Any) -> Any:
        if isinstance(data, dict) and "requires_edition" in data:
            raise ValueError(_REQUIRES_EDITION_MIGRATION_ERROR)
        return data


class GitRepo(_LegacyEditionKeyRejector):
    model_config = ConfigDict(extra="forbid")

    url: str
    ref: str


class CoreLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["core"] = "core"
    url: str = "https://github.com/odoo/odoo.git"
    ref: str | None = None


class EnterpriseLayer(BaseModel):
    """Singleton enterprise source, sibling of `core:`. Never user-listed
    under `layers:`; composed at chain position 2 (`core -> enterprise ->
    layers -> client`) only when `Manifest.edition == "enterprise"`."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["enterprise"] = "enterprise"
    url: str
    ref: str | None = None


# Additive, optional projection-mount classification (Phase 2 Slice 3). Absent
# on all Slice 1/2a/2b fixtures — defaults to `None`, which `classify_root`
# treats as "custom".
LayerCategory = Literal["custom", "community", "localization", "enterprise"]


class PublishedLayer(_LegacyEditionKeyRejector):
    model_config = ConfigDict(extra="forbid")

    type: Literal["published"]
    name: str
    source: str
    version: str
    requires_enterprise: bool = False
    category: LayerCategory | None = None


class GitLayer(_LegacyEditionKeyRejector):
    model_config = ConfigDict(extra="forbid")

    type: Literal["git"]
    name: str
    repos: list[GitRepo]
    requires_enterprise: bool = False
    category: LayerCategory | None = None


# NOTE: `CoreLayer` is intentionally NOT a member of this discriminated union.
# Despite sharing the "Layer" suffix and a `type` discriminator, core is a
# singleton composed separately (always first in the chain, with defaults) and
# is never user-listed under `layers:`. Keeping it out of the union avoids
# accepting a second `type: core` entry inside `layers`.
Layer = Annotated[PublishedLayer | GitLayer, Field(discriminator="type")]


class Client(BaseModel):
    # `type` tags the client so the composed chain (core -> layers -> client)
    # is uniformly discriminable by `.type`, mirroring the layer models.
    type: Literal["client"] = "client"
    addons_path: Path
    python_requirements: Path | None = None


class Override(BaseModel):
    layer: str
    repo: str
    fork: str
    ref: str


class Workspace(BaseModel):
    checkout_timeout_seconds: int | None = Field(default=None, gt=0)


DEFAULT_ODOO_BIND_HOST = "127.0.0.1"


class OdooBackendConfig(BaseModel):
    http_port: int | None = Field(default=None, gt=0, le=65535)
    bind_host: str = Field(default=DEFAULT_ODOO_BIND_HOST, strict=True)

    @field_validator("bind_host")
    @classmethod
    def validate_bind_host(cls, value: str) -> str:
        try:
            ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError as exc:
            raise ValueError("bind_host must be a valid IPv4 address") from exc
        return value


class BackendConfig(BaseModel):
    odoo: OdooBackendConfig | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    odoo_version: str
    edition: Literal["community", "enterprise"]
    core: CoreLayer = CoreLayer()
    enterprise: EnterpriseLayer | None = None
    layers: list[Layer] = []
    client: Client
    overrides: list[Override] = []
    workspace: Workspace | None = None
    backend: BackendConfig | None = None

    @model_validator(mode="after")
    def _validate_enterprise_block(self) -> "Manifest":
        if self.edition == "enterprise" and self.enterprise is None:
            raise ValueError(
                "edition 'enterprise' requires a top-level 'enterprise:' block (url, ref)"
            )
        if self.edition != "enterprise" and self.enterprise is not None:
            raise ValueError("'enterprise:' block is only allowed when edition is 'enterprise'")
        return self


__all__ = [
    "GitRepo",
    "LayerCategory",
    "CoreLayer",
    "EnterpriseLayer",
    "PublishedLayer",
    "GitLayer",
    "Layer",
    "Client",
    "Override",
    "Workspace",
    "OdooBackendConfig",
    "DEFAULT_ODOO_BIND_HOST",
    "BackendConfig",
    "Manifest",
]
