"""Provider-owned immutable database lifecycle values.

`ResourceOwnership`, `OperationIdentity`, and `CreationReceipt` are canonically defined in
`odoo_forge.resource_ownership.types` (platform-scope `CAP-RESOURCE-OWNERSHIP` vocabulary) and
re-exported here so every existing importer keeps resolving them through this module unchanged.
"""

import re

from pydantic import BaseModel, ConfigDict, field_validator

from odoo_forge.resource_ownership.types import (
    CreationReceipt,
    OperationIdentity,
    ResourceOwnership,
)

_RESIDUAL_FAILURE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_SENSITIVE_RESIDUAL_TERMS = (
    "artifact",
    "bytes",
    "credential",
    "dump",
    "password",
    "secret",
    "token",
)


class _ProviderValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class DatabaseSpec(_ProviderValue):
    name: str


class DatabaseRef(_ProviderValue):
    """Opaque identifier and ownership metadata for a provider database."""

    identifier: str
    ownership: ResourceOwnership


class DatabaseCreation(_ProviderValue):
    """Opaque handoff joining a provider reference and its creation receipt."""

    ref: DatabaseRef
    receipt: CreationReceipt


class CleanupReport(_ProviderValue):
    residual_failures: tuple[str, ...] = ()

    @field_validator("residual_failures", mode="before")
    @classmethod
    def validate_residual_failures(cls, values: object) -> object:
        if not isinstance(values, (tuple, list)):
            raise ValueError(
                "cleanup residual failures must be a sequence of safe opaque identifiers"
            )
        for value in values:
            if not isinstance(value, str):
                raise ValueError("cleanup residual failures must be safe opaque identifiers")
            lowered = value.lower()
            if _RESIDUAL_FAILURE_IDENTIFIER.fullmatch(value) is None or any(
                term in lowered for term in _SENSITIVE_RESIDUAL_TERMS
            ):
                raise ValueError("cleanup residual failures must be safe opaque identifiers")
        return values


__all__ = [
    "CleanupReport",
    "CreationReceipt",
    "DatabaseCreation",
    "DatabaseRef",
    "DatabaseSpec",
    "OperationIdentity",
    "ResourceOwnership",
]
