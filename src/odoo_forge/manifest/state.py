"""In-memory representation of a materialized (on-disk) workspace state.

Populated by an adapter in a later slice; `detect_drift` only ever
consumes these as plain in-memory models, never touching disk itself.
"""

from pydantic import BaseModel


class MaterializedRepo(BaseModel):
    url: str
    commit: str


class MaterializedLayer(BaseModel):
    # Mirrors `ResolvedLayer`/`ResolvedRepo`: a layer tracks one commit per
    # repo, so multi-repo layers can be drift-checked repo-by-repo.
    name: str
    repos: list[MaterializedRepo] = []


class MaterializedState(BaseModel):
    layers: list[MaterializedLayer] = []


__all__ = ["MaterializedState", "MaterializedLayer", "MaterializedRepo"]
