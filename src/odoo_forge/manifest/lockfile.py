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


# Bumped whenever the `project.lock` on-disk shape changes. Absent on a
# legacy (pre-Slice-2a) lock document, which validates as version 1.
LOCKFILE_SCHEMA_VERSION = 1


class Lockfile(BaseModel):
    schema_version: int = LOCKFILE_SCHEMA_VERSION
    generated_from: str
    layers: list[ResolvedLayer] = []

    def to_canonical_json(self) -> str:
        """Canonical, byte-stable `project.lock` serialization.

        Sorted dict keys + fixed indent for a diff/git-friendly on-disk file.
        List order (e.g. `layers`) is semantically meaningful and preserved —
        `sort_keys` only reorders dict keys, never list elements.
        """
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"

    @classmethod
    def from_json(cls, raw: str) -> "Lockfile":
        return cls.model_validate(json.loads(raw))


__all__ = [
    "compute_manifest_hash",
    "ResolvedRepo",
    "ResolvedLayer",
    "Lockfile",
    "LOCKFILE_SCHEMA_VERSION",
]
