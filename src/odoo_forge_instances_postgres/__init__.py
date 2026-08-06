"""Instance registry PostgreSQL schema and migration package (inert marker)."""

from .errors import (
    AuthorityTableRejectedError,
    CatalogVerificationError,
    MigrationAutocommitError,
    MigrationLockTimeoutError,
    RegistryTableRejectedError,
)

__all__ = [
    "MigrationAutocommitError",
    "MigrationLockTimeoutError",
    "RegistryTableRejectedError",
    "AuthorityTableRejectedError",
    "CatalogVerificationError",
]
