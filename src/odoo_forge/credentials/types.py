"""Opaque references owned by the credential capability."""

from typing import NewType

CredentialHandle = NewType("CredentialHandle", str)


__all__ = ["CredentialHandle"]
