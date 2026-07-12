"""Opaque references and immutable values owned by the data-artifact capability."""

import re

from pydantic import BaseModel, ConfigDict

_SAFE_ARTIFACT_REF = re.compile(r"^[A-Za-z0-9_-]+$")
_HOSTNAME_TEXT = re.compile(
    r"\b(?:localhost|(?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]+|[A-Za-z0-9-]+:\d+)\b"
)
_CREDENTIAL_SHAPED_TEXT = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_SECRET_OR_CONNECTION_TEXT = re.compile(
    r"(?:\b(?:api[_-]?key|authorization|bearer|credential|password|passwd|secret|token)\b\s*[=:]?|://|@)",
    re.IGNORECASE,
)


def require_safe_opaque_identifier(value: str, field_name: str) -> str:
    if (
        not value
        or not _SAFE_ARTIFACT_REF.fullmatch(value)
        or _SECRET_OR_CONNECTION_TEXT.search(value)
        or _HOSTNAME_TEXT.search(value)
        or _CREDENTIAL_SHAPED_TEXT.search(value)
    ):
        raise ValueError(f"{field_name} must be a safe opaque identifier")
    return value


class DataArtifactRef(str):
    def __new__(cls, value: str) -> "DataArtifactRef":
        require_safe_opaque_identifier(value, "data artifact reference")
        return str.__new__(cls, value)


class _ArtifactValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


__all__ = [
    "DataArtifactRef",
    "_ArtifactValue",
    "_SECRET_OR_CONNECTION_TEXT",
    "require_safe_opaque_identifier",
]
