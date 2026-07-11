"""Typed errors whose public details never expose credential material."""


class CredentialError(Exception):
    """Base error that discards unsafe provider diagnostics."""

    public_detail = "credential operation failed"

    def __init__(self, diagnostic: str = "") -> None:
        self.detail = self.public_detail
        super().__init__(self.detail)


class CredentialUnavailableError(CredentialError):
    public_detail = "credential material is unavailable"


class CredentialTargetRejectedError(CredentialError):
    public_detail = "credential target does not accept an opaque reference"


__all__ = [
    "CredentialError",
    "CredentialTargetRejectedError",
    "CredentialUnavailableError",
]
