"""Canonical, provider-neutral resource-ownership values.

This module is the platform-scope vocabulary anchor for `CAP-RESOURCE-OWNERSHIP`. It
generalizes the ownership state model, receipt shape, and identity primitives that were
originally defined database-only in `odoo_forge.database.types` so any managed resource kind
(databases, backend containers, image registry entries, future remote/K8s targets) can share
one contract. `odoo_forge.database.types` re-exports the relocated names for backward
compatibility; this module owns their canonical definitions.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from odoo_forge.durable_operations.types import DurableOperationIdentity


class _OwnershipValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ResourceOwnership(StrEnum):
    """Exactly three ownership states shared by every resource kind. No others in v1."""

    CREATED = "created"
    ADOPTED = "adopted"
    EXTERNAL = "external"


class OperationIdentity(_OwnershipValue):
    value: str


class CreationReceipt(_OwnershipValue):
    """Opaque operation proof used to reconcile or clean up a database."""

    operation: OperationIdentity
    owned_resource_ids: tuple[str, ...]


class ResourceRef(_OwnershipValue):
    """Opaque identifier, resource kind, and ownership metadata for any managed resource."""

    identifier: str
    resource_kind: str = Field(min_length=1)
    ownership: ResourceOwnership


class TenantAttribution(_OwnershipValue):
    """Optional tenant link composed with ownership; never mandatory at ownership time."""

    tenant_id: str | None = None


class OwnershipReceipt(_OwnershipValue):
    """Reusable receipt: opaque operation proof, owned ids, and a live-proof expectation.

    The operation proof reuses `CAP-DURABLE-OPERATIONS`' stable `DurableOperationIdentity`
    rather than authoring a competing identity model. The concrete live-proof mechanism
    (e.g. Docker labels) stays an adapter concern and is never encoded here.
    """

    operation: DurableOperationIdentity
    owned_resource_ids: tuple[str, ...]
    live_proof_expected: bool = True


class OwnershipRecord(_OwnershipValue):
    """Current read-only view of a resource's ownership state and evidence."""

    ref: ResourceRef
    attribution: TenantAttribution | None = None
    receipt: OwnershipReceipt | None = None


class OwnershipAttestation(_OwnershipValue):
    """Redacted result proving whether a receipt currently establishes ownership."""

    resource: ResourceRef
    attested: bool
    live_proof_verified: bool


__all__ = [
    "CreationReceipt",
    "OperationIdentity",
    "OwnershipAttestation",
    "OwnershipReceipt",
    "OwnershipRecord",
    "ResourceOwnership",
    "ResourceRef",
    "TenantAttribution",
]
