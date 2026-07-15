"""Lockfile domain and pure manifest hashing.

`compute_manifest_hash` hashes the in-memory `Manifest` model, never raw
file bytes — two `project.yaml` files that parse to an equal `Manifest`
(different whitespace/key order) MUST hash identically.
"""

import hashlib
import json
from typing import Any, Literal, Self, overload

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.config import ExtraValues

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


class ResolvedGitLayer(BaseModel):
    name: str
    repos: list[ResolvedRepo] = Field(default_factory=list)


class ResolvedPublishedLayer(BaseModel):
    name: str
    source: str
    version: str
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


# Compatibility name for existing Git-only callers. New code should use the
# explicit Git-layer name so it cannot be confused with published entries.
ResolvedLayer = ResolvedGitLayer


class LockfileV1(BaseModel):
    """The Git-only `project.lock` format retained for backwards-compatible reads."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    generated_from: str
    layers: list[ResolvedGitLayer] = Field(default_factory=list)


class LockfileV2(BaseModel):
    """The current `project.lock` format, with distinct Git and published entries."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    generated_from: str
    git_layers: list[ResolvedGitLayer] = Field(default_factory=list)
    published_layers: list[ResolvedPublishedLayer] = Field(default_factory=list)


LOCKFILE_SCHEMA_VERSION = 2


class Lockfile(BaseModel):
    """Normalized lockfile domain model with explicit versioned serialization."""

    model_config = ConfigDict(validate_by_name=True)

    schema_version: Literal[1, 2] = 2
    generated_from: str
    git_layers: list[ResolvedGitLayer] = Field(
        default_factory=list,
        validation_alias=AliasChoices("git_layers", "layers"),
    )
    published_layers: list[ResolvedPublishedLayer] = Field(default_factory=list)

    @overload
    def __init__(
        self,
        *,
        generated_from: str,
        schema_version: Literal[1, 2] = 2,
        git_layers: list[ResolvedGitLayer] = ...,
        published_layers: list[ResolvedPublishedLayer] = ...,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        generated_from: str,
        layers: list[ResolvedGitLayer],
        schema_version: Literal[1, 2] = 2,
        published_layers: list[ResolvedPublishedLayer] = ...,
    ) -> None: ...

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    @property
    def layers(self) -> list[ResolvedGitLayer]:
        """Compatibility view for Git-only lock consumers until their migration."""
        return self.git_layers

    def to_canonical_json(self) -> str:
        """Canonical, byte-stable `project.lock` serialization.

        Sorted dict keys + fixed indent for a diff/git-friendly on-disk file.
        List order (e.g. `git_layers`) is semantically meaningful and preserved —
        `sort_keys` only reorders dict keys, never list elements.
        """
        if self.schema_version == 1:
            if self.published_layers:
                raise ValueError("lockfile schema version 1 cannot contain published layers")
            document = LockfileV1(
                generated_from=self.generated_from,
                layers=self.git_layers,
            ).model_dump(mode="json")
        else:
            document = LockfileV2(
                generated_from=self.generated_from,
                git_layers=self.git_layers,
                published_layers=self.published_layers,
            ).model_dump(mode="json")
        return json.dumps(document, sort_keys=True, indent=2) + "\n"

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """Treat direct validation of pre-versioned dictionaries as v1 too."""
        if isinstance(obj, dict) and "schema_version" not in obj:
            obj = {"schema_version": 1, **obj}
        return super().model_validate(
            obj,
            strict=strict,
            extra=extra,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Lockfile":
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("lockfile document must be a JSON object")

        version = document.get("schema_version", 1)
        if type(version) is not int:
            raise ValueError("lockfile schema_version must be an integer")
        if version == 1:
            legacy = LockfileV1.model_validate(document)
            return cls(
                schema_version=legacy.schema_version,
                generated_from=legacy.generated_from,
                git_layers=legacy.layers,
            )
        if version == 2:
            current = LockfileV2.model_validate(document)
            return cls(
                schema_version=current.schema_version,
                generated_from=current.generated_from,
                git_layers=current.git_layers,
                published_layers=current.published_layers,
            )
        raise ValueError(f"unsupported lockfile schema version: {version}")


__all__ = [
    "compute_manifest_hash",
    "ResolvedRepo",
    "ResolvedGitLayer",
    "ResolvedPublishedLayer",
    "ResolvedLayer",
    "LockfileV1",
    "LockfileV2",
    "Lockfile",
    "LOCKFILE_SCHEMA_VERSION",
]
