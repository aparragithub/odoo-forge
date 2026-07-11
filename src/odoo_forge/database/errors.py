"""Typed, redacted failures for database provider contracts."""


class DatabaseProviderError(Exception):
    """Base error whose public detail never exposes provider diagnostics."""

    public_detail = "database provider operation failed"

    def __init__(self, diagnostic: str = "") -> None:
        self.detail = self.public_detail
        super().__init__(self.detail)


class InvalidDatabaseRequestError(DatabaseProviderError):
    public_detail = "database request is invalid"


class CredentialUnavailableError(DatabaseProviderError):
    public_detail = "database credentials are unavailable"


class ArtifactUnavailableError(DatabaseProviderError):
    public_detail = "database artifact is unavailable"


class ResourceUnavailableError(DatabaseProviderError):
    public_detail = "database resource is unavailable"


class DatabaseConflictError(DatabaseProviderError):
    public_detail = "database resource conflicts with the requested operation"


class DatabaseReadinessError(DatabaseProviderError):
    public_detail = "database resource is not ready"


class OwnershipRefusedError(DatabaseProviderError):
    public_detail = "database resource ownership does not permit this operation"


class DatabaseOperationError(DatabaseProviderError):
    public_detail = "database provider operation failed"


class IncompleteCleanupError(DatabaseProviderError):
    public_detail = "database cleanup incomplete"


__all__ = [
    "ArtifactUnavailableError",
    "CredentialUnavailableError",
    "DatabaseConflictError",
    "DatabaseOperationError",
    "DatabaseProviderError",
    "DatabaseReadinessError",
    "IncompleteCleanupError",
    "InvalidDatabaseRequestError",
    "OwnershipRefusedError",
    "ResourceUnavailableError",
]
