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
    # `sort_keys=True` is a forward-looking guard, not currently load-bearing:
    # Pydantic's `model_dump` already emits fields in declared order, so today's
    # flat models would hash identically without it. It protects determinism the
    # moment any dict-typed field (unordered) is added to the schema, where JSON
    # key order would otherwise depend on insertion order. `separators` drops
    # incidental whitespace. Input-side key-order stability (two YAML files with
    # different key order parsing to an equal Manifest) is guaranteed by Pydantic
    # validation, and is covered by test_hash_stable_across_key_order.
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
