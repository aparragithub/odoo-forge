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
    """Opaque handles required by the local backend planner.

    Postgres credential injection is owned exclusively by the
    `odoo_forge_postgres_docker` adapter's `PostgreSQLSecretInjection`
    (CAP-DATABASE-RUNTIME-CUTOVER, design "Credential convergence"); the
    postgres handle travels through `BackendPlan.postgres_credentials`
    instead of this binding set.
    """

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
