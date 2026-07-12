"""Pure-domain contract for coherent data-artifact restore sets."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import field_validator, model_validator

from odoo_forge.data_artifacts.types import (
    _SECRET_OR_CONNECTION_TEXT,
    DataArtifactRef,
    _ArtifactValue,
    require_safe_opaque_identifier,
)

_DIGEST_LENGTHS = {"sha256": 64, "sha512": 128}
_BEARER_TOKEN_TEXT = re.compile(r"\bauthorization\b\s*:?\s*bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE)


def _require_opaque_identifier(value: str, field_name: str) -> str:
    if any(char.isspace() for char in value):
        raise ValueError(f"{field_name} must be a safe opaque identifier")
    return require_safe_opaque_identifier(value, field_name)


def _require_redacted_detail(value: str | None) -> str | None:
    if value is not None and (
        _SECRET_OR_CONNECTION_TEXT.search(value)
        or _BEARER_TOKEN_TEXT.search(value)
        or re.search(
            r"(?:\b(?:localhost|(?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]+|[A-Za-z0-9-]+:\d+)\b|\[[0-9A-Fa-f:]+\]:\d+)",
            value,
        )
    ):
        raise ValueError("redacted detail must not contain secret-bearing or connection text")
    return value


class ArtifactComponentKind(StrEnum):
    DATABASE = "database"
    FILESTORE = "filestore"


class ValidationFailureCode(StrEnum):
    UNAVAILABLE = "unavailable"
    INTEGRITY_FAILED = "integrity_failed"
    COHERENCE_FAILED = "coherence_failed"
    INCOMPLETE = "incomplete"
    UNSUPPORTED_FORMAT = "unsupported_format"


class DiscardOutcomeCode(StrEnum):
    COMPLETED = "completed"
    REFUSED = "refused"
    RESIDUAL_FAILURE = "residual_failure"


class ArtifactDigest(_ArtifactValue):
    algorithm: str
    value: str

    @model_validator(mode="after")
    def require_supported_digest(self) -> ArtifactDigest:
        expected_length = _DIGEST_LENGTHS.get(self.algorithm)
        is_valid_hex = re.fullmatch(r"[0-9a-fA-F]+", self.value) is not None
        if expected_length is None or not is_valid_hex or len(self.value) != expected_length:
            raise ValueError("digest must use a supported algorithm and valid hexadecimal value")
        return self


class RestoreSetComponent(_ArtifactValue):
    kind: ArtifactComponentKind
    opaque_component_ref: str
    format_version: str
    digest: ArtifactDigest

    @model_validator(mode="after")
    def require_safe_component_metadata(self) -> RestoreSetComponent:
        _require_opaque_identifier(self.opaque_component_ref, "component reference")
        if not self.format_version or _SECRET_OR_CONNECTION_TEXT.search(self.format_version):
            raise ValueError("format version must be present and safe")
        return self


class RestoreSetManifest(_ArtifactValue):
    restore_set_id: str
    lineage_id: str
    components: tuple[RestoreSetComponent, ...]

    @model_validator(mode="after")
    def require_database_and_filestore(self) -> RestoreSetManifest:
        _require_opaque_identifier(self.restore_set_id, "restore set id")
        _require_opaque_identifier(self.lineage_id, "lineage id")
        kinds = tuple(component.kind for component in self.components)
        if len(kinds) != 2 or set(kinds) != {
            ArtifactComponentKind.DATABASE,
            ArtifactComponentKind.FILESTORE,
        }:
            raise ValueError("restore set must contain one database and one filestore component")
        return self


class RestoreReadiness(_ArtifactValue):
    ready: bool
    manifest: RestoreSetManifest | None
    failure_code: ValidationFailureCode | None
    redacted_detail: str | None

    @model_validator(mode="after")
    def require_consistent_readiness(self) -> RestoreReadiness:
        _require_redacted_detail(self.redacted_detail)
        if self.ready and (self.manifest is None or self.failure_code is not None):
            raise ValueError("ready restore inputs require a manifest and no failure code")
        if not self.ready and (self.manifest is not None or self.failure_code is None):
            raise ValueError("unready restore inputs require a failure code and no manifest")
        return self


class DiscardOutcome(_ArtifactValue):
    code: DiscardOutcomeCode
    residual_ids: tuple[str, ...] = ()
    redacted_detail: str | None = None

    @field_validator("residual_ids")
    @classmethod
    def require_opaque_residual_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _require_opaque_identifier(value, "residual id")
        return values

    @model_validator(mode="after")
    def require_consistent_discard_outcome(self) -> DiscardOutcome:
        _require_redacted_detail(self.redacted_detail)
        if self.code is DiscardOutcomeCode.COMPLETED and self.residual_ids:
            raise ValueError("completed discard outcomes cannot have residual ids")
        if self.code is DiscardOutcomeCode.RESIDUAL_FAILURE and not self.residual_ids:
            raise ValueError("residual discard failures require residual ids")
        return self


@runtime_checkable
class DataArtifactCapability(Protocol):
    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest: ...

    def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness: ...

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome: ...


__all__ = [
    "ArtifactComponentKind",
    "ArtifactDigest",
    "DataArtifactCapability",
    "DiscardOutcome",
    "DiscardOutcomeCode",
    "RestoreReadiness",
    "RestoreSetComponent",
    "RestoreSetManifest",
    "ValidationFailureCode",
]
