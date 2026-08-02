"""Instance registry PostgreSQL schema and migration package (inert marker)."""

from .errors import (
    CatalogVerificationError,
    MigrationAutocommitError,
    MigrationLockTimeoutError,
    RegistryTableRejectedError,
)

__all__ = [
    "MigrationAutocommitError",
    "MigrationLockTimeoutError",
    "RegistryTableRejectedError",
    "CatalogVerificationError",
]
