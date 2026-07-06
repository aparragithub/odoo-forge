"""In-memory representation of a materialized (on-disk) workspace state.

Populated by an adapter in a later slice; `detect_drift` only ever
consumes these as plain in-memory models, never touching disk itself.
"""

from pydantic import BaseModel


class MaterializedLayer(BaseModel):
    name: str
    commit: str


class MaterializedState(BaseModel):
    layers: list[MaterializedLayer] = []


__all__ = ["MaterializedState", "MaterializedLayer"]
