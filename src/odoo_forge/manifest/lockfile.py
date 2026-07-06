"""Lockfile domain and pure manifest hashing.

`compute_manifest_hash` hashes the in-memory `Manifest` model, never raw
file bytes — two `project.yaml` files that parse to an equal `Manifest`
(different whitespace/key order) MUST hash identically.
"""

import hashlib
import json

from pydantic import BaseModel

from odoo_forge.manifest.schema import Manifest


def compute_manifest_hash(manifest: Manifest) -> str:
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class ResolvedRepo(BaseModel):
    url: str
    ref: str
    commit: str


class ResolvedLayer(BaseModel):
    name: str
    repos: list[ResolvedRepo] = []


class Lockfile(BaseModel):
    generated_from: str
    layers: list[ResolvedLayer] = []


__all__ = ["compute_manifest_hash", "ResolvedRepo", "ResolvedLayer", "Lockfile"]
