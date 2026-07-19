"""Provider-neutral read/attest contract for `CAP-RESOURCE-OWNERSHIP`.

`ResourceOwnershipPort` v1 exposes ownership state and receipt/evidence read and attestation
semantics only. It MUST NOT define runtime authority for transition verbs (`reserve`, `bind`,
`activate`, `retire`, `adopt`); those verbs are deferred to `SP-CONTROL-PLANE-AUTHORITY`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from odoo_forge.resource_ownership.types import (
    OwnershipAttestation,
    OwnershipReceipt,
    OwnershipRecord,
    ResourceRef,
)


@runtime_checkable
class ResourceOwnershipPort(Protocol):
    """Read ownership state and attest receipts without mutating or transitioning state."""

    def describe_ownership(self, resource: ResourceRef) -> OwnershipRecord:
        """Return the current ownership state and optional tenant attribution. No side effects."""
        ...

    def attest_ownership(self, receipt: OwnershipReceipt) -> OwnershipAttestation:
        """Verify the operation proof, owned-id membership, and live-proof expectation.

        MUST NOT mutate or transition ownership state; returns a redacted attestation.
        """
        ...


__all__ = ["ResourceOwnershipPort"]
