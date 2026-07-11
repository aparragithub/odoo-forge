"""SOPS-backed opaque credential handoff for ref-capable targets."""

from odoo_forge.credentials.errors import CredentialTargetRejectedError
from odoo_forge.credentials.types import (
    CredentialHandle,
    CredentialInjectionDescriptor,
    TargetContext,
)

_SOPS_REF_CAPABLE_TARGET_KINDS = frozenset({"database"})


def materialize_for_target(
    handle: CredentialHandle,
    target: TargetContext,
) -> CredentialInjectionDescriptor:
    """Return a SOPS reference without materializing plaintext to the consumer."""
    if target.kind not in _SOPS_REF_CAPABLE_TARGET_KINDS:
        raise CredentialTargetRejectedError()

    plaintext_slots: list[str] = []
    try:
        return CredentialInjectionDescriptor(
            handle=handle,
            target_kind=target.kind,
            store_ref=_sops_store_ref(handle),
            redaction_label="SOPS credential",
        )
    finally:
        _clear_plaintext(plaintext_slots)


def _sops_store_ref(handle: CredentialHandle) -> str:
    """Build the opaque SOPS reference consumed by a target-native injector."""
    return f"sops://{handle}"


def _clear_plaintext(plaintext_slots: list[str]) -> None:
    """Drop a capability-local plaintext reference after an operation ends."""
    plaintext_slots.clear()


__all__ = ["materialize_for_target"]
