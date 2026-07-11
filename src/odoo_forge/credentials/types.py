"""Opaque values owned by the credential capability."""

from typing import Literal, NewType

from pydantic import BaseModel, ConfigDict

CredentialHandle = NewType("CredentialHandle", str)


class _OpaqueCredentialValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class BackendCredentialBindings(_OpaqueCredentialValue):
    """Opaque handles required by the local backend planner."""

    postgres_password: CredentialHandle
    odoo_db_password: CredentialHandle


class TargetContext(_OpaqueCredentialValue):
    kind: Literal["database", "backend", "identity", "pipeline"]
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
    "TargetContext",
]
