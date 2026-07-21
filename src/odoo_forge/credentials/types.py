"""Opaque values owned by the credential capability."""

from collections.abc import Callable
from typing import Literal, NewType

from pydantic import BaseModel, ConfigDict

CredentialHandle = NewType("CredentialHandle", str)

# Single source of truth for the handle->plaintext resolver shape. Every
# adapter that resolves a `CredentialHandle` against the SOPS+age store
# (git askpass injection, Docker env-file injection, the doctor check) must
# import this alias rather than redefine it locally.
CredentialResolver = Callable[[CredentialHandle], str]


class _OpaqueCredentialValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class BackendCredentialBindings(_OpaqueCredentialValue):
    """Opaque handles required by the local backend planner."""

    postgres_password: CredentialHandle
    odoo_db_password: CredentialHandle


class TargetContext(_OpaqueCredentialValue):
    kind: Literal["database", "backend", "identity", "pipeline", "source"]
    target_id: str


class CredentialInjectionDescriptor(_OpaqueCredentialValue):
    handle: CredentialHandle
    target_kind: str
    store_ref: str
    redaction_label: str


__all__ = [
    "BackendCredentialBindings",
    "CredentialHandle",
    "CredentialInjectionDescriptor",
    "CredentialResolver",
    "TargetContext",
]
