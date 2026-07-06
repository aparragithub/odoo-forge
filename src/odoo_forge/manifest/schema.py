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


class PublishedLayer(BaseModel):
    type: Literal["published"]
    name: str
    source: str
    version: str
    requires_edition: Literal["enterprise"] | None = None


class GitLayer(BaseModel):
    type: Literal["git"]
    name: str
    repos: list[GitRepo]
    requires_edition: Literal["enterprise"] | None = None


Layer = Annotated[PublishedLayer | GitLayer, Field(discriminator="type")]


class Client(BaseModel):
    addons_path: Path
    python_requirements: Path | None = None


class Override(BaseModel):
    layer: str
    repo: str
    fork: str
    ref: str


class Manifest(BaseModel):
    name: str
    odoo_version: str
    edition: Literal["community", "enterprise"]
    core: CoreLayer = CoreLayer()
    layers: list[Layer] = []
    client: Client
    overrides: list[Override] = []


__all__ = [
    "GitRepo",
    "CoreLayer",
    "PublishedLayer",
    "GitLayer",
    "Layer",
    "Client",
    "Override",
    "Manifest",
]
