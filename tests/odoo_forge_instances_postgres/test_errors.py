"""Public contracts for the shared PostgreSQL migration errors."""

from __future__ import annotations

import odoo_forge_instances_postgres as package
from odoo_forge_instances_postgres import errors, migrate

ERROR_NAMES = [
    "MigrationAutocommitError",
    "MigrationLockTimeoutError",
    "RegistryTableRejectedError",
    "AuthorityTableRejectedError",
    "CatalogVerificationError",
]
ERRORS = tuple(getattr(errors, name) for name in ERROR_NAMES)


def test_errors_have_the_exact_public_vocabulary() -> None:
    assert errors.__all__ == ERROR_NAMES
    assert package.__all__ == ERROR_NAMES
    assert [error.__name__ for error in ERRORS] == ERROR_NAMES


def test_errors_preserve_exception_construction_and_message() -> None:
    message = "migration contract failure"

    for error in ERRORS:
        instance = error(message)

        assert issubclass(error, Exception)
        assert instance.args == (message,)
        assert str(instance) == message


def test_all_supported_import_paths_share_class_identity() -> None:
    for name in errors.__all__:
        shared = getattr(errors, name)

        assert getattr(migrate, name) is shared
        assert getattr(package, name) is shared
