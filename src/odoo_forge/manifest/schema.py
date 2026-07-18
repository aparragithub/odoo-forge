"""Pure Pydantic v2 schema for `project.yaml` — the manifest domain.

No git/docker/network access. Every model here describes intent only;
resolution (SHAs, branch names) happens during composition/materialization
in later slices.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class GitRepo(BaseModel):
    url: str
    ref: str
    requires_edition: Literal["enterprise"] | None = None


class CoreLayer(BaseModel):
    type: Literal["core"] = "core"
    url: str = "https://github.com/odoo/odoo.git"
    ref: str | None = None


# Additive, optional projection-mount classification (Phase 2 Slice 3). Absent
# on all Slice 1/2a/2b fixtures — defaults to `None`, which `classify_root`
# treats as "custom". Distinct from `requires_edition`: `requires_edition ==
# "enterprise"` always overrides `category` when classifying a mount root.
LayerCategory = Literal["custom", "community", "localization", "enterprise"]


class PublishedLayer(BaseModel):
    type: Literal["published"]
    name: str
    source: str
    version: str
    requires_edition: Literal["enterprise"] | None = None
    category: LayerCategory | None = None


class GitLayer(BaseModel):
    type: Literal["git"]
    name: str
    repos: list[GitRepo]
    requires_edition: Literal["enterprise"] | None = None
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


class Manifest(BaseModel):
    name: str
    odoo_version: str
    edition: Literal["community", "enterprise"]
    core: CoreLayer = CoreLayer()
    layers: list[Layer] = []
    client: Client
    overrides: list[Override] = []
    workspace: Workspace | None = None


__all__ = [
    "GitRepo",
    "LayerCategory",
    "CoreLayer",
    "PublishedLayer",
    "GitLayer",
    "Layer",
    "Client",
    "Override",
    "Workspace",
    "Manifest",
]
