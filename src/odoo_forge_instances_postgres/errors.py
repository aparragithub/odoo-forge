"""Typed errors raised by the instance-registry migration."""

from __future__ import annotations

__all__ = [
    "MigrationAutocommitError",
    "MigrationLockTimeoutError",
    "RegistryTableRejectedError",
    "AuthorityTableRejectedError",
    "CatalogVerificationError",
]


class MigrationAutocommitError(Exception):
    """Raised when ``run_migration`` is invoked on an autocommit connection."""


class MigrationLockTimeoutError(Exception):
    """Raised when a lock wait exceeds ``lock_timeout`` (SQLSTATE 55P03)."""


class RegistryTableRejectedError(Exception):
    """Raised when the existing registry table fails the catalog predicate."""


class AuthorityTableRejectedError(Exception):
    """Raised when an authority table is not exactly compatible with its owner."""


class CatalogVerificationError(Exception):
    """Raised when the catalog predicate returns no matching relation."""
