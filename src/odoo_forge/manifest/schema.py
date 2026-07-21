"""Pure Pydantic v2 schema for `project.yaml` — the manifest domain.

No git/docker/network access. Every model here describes intent only;
resolution (SHAs, branch names) happens during composition/materialization
in later slices.
"""

import ipaddress
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

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
    url: str = "https://github.com/odoo/enterprise.git"
    ref: str | None = None


_CATEGORY_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_CATEGORY_MAX_LENGTH = 63


def _normalize_category(value: str | None) -> str:
    """Normalize + validate a layer `category`. `None` defaults to `"custom"`.

    Validation is deliberately minimal: slug shape (lowercase alphanumeric,
    optionally hyphenated, no leading/trailing hyphen) and a length bound —
    nothing else. There is intentionally NO reserved-name blocklist for
    "community"/"enterprise"/"worktrees" (the system mount roots). Under the
    pure mount model every user-declared layer nests under
    `/mnt/custom/<category>/`, so even a category literally named
    "community" only ever produces a plain subfolder there
    (`/mnt/custom/community`) and can never collide with a system root —
    the collision this blocklist would have prevented is structurally
    impossible once nesting is in place.
    """
    resolved = "custom" if value is None else value
    if len(resolved) > _CATEGORY_MAX_LENGTH or not _CATEGORY_PATTERN.match(resolved):
        raise ValueError(
            "category must be a lowercase alphanumeric slug (optionally "
            f"hyphenated), at most {_CATEGORY_MAX_LENGTH} characters; got {resolved!r}"
        )
    return resolved


# Validated free-form slug string, not a closed enum. `None` normalizes to
# `"custom"` (the default namespace). See `_normalize_category` for the full
# validation rationale.
LayerCategory = Annotated[str, BeforeValidator(_normalize_category)]


# System/structural mount roots (see `projection.build_mount_roots`). Declared
# here — alongside the category type — so `Manifest` can validate
# `mount_priority` keys without importing `projection` (which imports this
# module). `worktrees` is reserved for `unlock`-promoted worktrees.
_SYSTEM_MOUNT_ROOTS = ("worktrees", "community", "enterprise")

_DEFAULT_CUSTOM_CATEGORY_DIR = "default"


def _custom_category_folder(category: str) -> str:
    """Map a validated layer `category` to its subfolder name under
    `/mnt/custom/`. Single source of truth for the folder mapping: the schema
    default `"custom"` (and an explicit `category: custom`) both resolve to
    the `"default"` subfolder, pinned so the two are indistinguishable on disk.
    """
    return _DEFAULT_CUSTOM_CATEGORY_DIR if category == "custom" else category


def _custom_root_key(category: str) -> str:
    """Map a validated layer `category` to its mount-root dict key
    (`custom/<folder>`). Pure mount model: every non-system layer nests under
    `/mnt/custom/`."""
    return f"custom/{_custom_category_folder(category)}"


class PublishedLayer(_LegacyEditionKeyRejector):
    model_config = ConfigDict(extra="forbid")

    type: Literal["published"]
    name: str
    source: str
    version: str
    requires_enterprise: bool = False
    category: LayerCategory = Field(default="custom", validate_default=True)


class GitLayer(_LegacyEditionKeyRejector):
    model_config = ConfigDict(extra="forbid")

    type: Literal["git"]
    name: str
    repos: list[GitRepo]
    requires_enterprise: bool = False
    category: LayerCategory = Field(default="custom", validate_default=True)


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
    # Ordered list of mount-root keys (`worktrees`/`community`/`enterprise` or a
    # declared `custom/<category>`) that take precedence in the runtime
    # `addons_path`. Entries appear first, in this exact order; unlisted roots
    # follow in the default order. Empty (default) preserves prior behavior.
    mount_priority: list[str] = []

    @model_validator(mode="after")
    def _validate_enterprise_block(self) -> "Manifest":
        if self.edition == "enterprise" and self.enterprise is None:
            # The official Odoo Enterprise repo is a system-provided source, not a
            # user choice: default it here so `edition: enterprise` needs no block.
            # A declared block (e.g. a fork) still overrides via its own `url`.
            self.enterprise = EnterpriseLayer()
        if self.edition != "enterprise" and self.enterprise is not None:
            raise ValueError("'enterprise:' block is only allowed when edition is 'enterprise'")
        return self

    @model_validator(mode="after")
    def _validate_mount_priority(self) -> "Manifest":
        valid = set(_SYSTEM_MOUNT_ROOTS)
        for layer in self.layers:
            valid.add(_custom_root_key(layer.category))
        seen: set[str] = set()
        for key in self.mount_priority:
            if key not in valid:
                raise ValueError(
                    f"mount_priority entry {key!r} is not a known mount root for this "
                    f"manifest; valid roots: {sorted(valid)}"
                )
            if key in seen:
                raise ValueError(f"mount_priority contains a duplicate entry {key!r}")
            seen.add(key)
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
