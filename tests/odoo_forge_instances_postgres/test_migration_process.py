"""Process-level import-purity and sync-only contracts."""

from __future__ import annotations

import subprocess
import sys

import pytest

MARKER_PACKAGES = (
    "odoo_forge_instances_postgres",
    "odoo_forge_instances_postgres.migrations",
)
MIGRATE_MODULE = "odoo_forge_instances_postgres.migrate"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


def _assert_clean_exit(code: str) -> None:
    result = _run(code)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "code",
    [
        "import odoo_forge_instances_postgres as p; "
        "assert p.__all__ == ['MigrationAutocommitError', 'MigrationLockTimeoutError', "
        "'RegistryTableRejectedError', 'AuthorityTableRejectedError', 'CatalogVerificationError']",
        "import odoo_forge_instances_postgres.migrations as p; assert p.__all__ == []",
        "import odoo_forge_instances_postgres.migrate as m; assert callable(m.run_migration)",
    ],
)
def test_imports_are_side_effect_free(code: str) -> None:
    _assert_clean_exit(code)


@pytest.mark.parametrize("marker", MARKER_PACKAGES)
def test_importing_a_marker_does_not_load_the_migration_module(marker: str) -> None:
    """Importing a marker package must leave the migration module unloaded."""

    _assert_clean_exit(
        f"import sys, {marker}; "
        f"assert {MIGRATE_MODULE!r} not in sys.modules, "
        f"'{marker} transitively imported the migration module'"
    )


def test_root_import_exports_errors_without_loading_runtime_modules() -> None:
    _assert_clean_exit(
        "import sys, odoo_forge_instances_postgres as p; "
        "assert 'odoo_forge_instances_postgres.migrate' not in sys.modules; "
        "assert 'asyncio' not in sys.modules; "
        "assert p.MigrationAutocommitError.__module__ == "
        "'odoo_forge_instances_postgres.errors'"
    )


def test_importing_the_migration_module_does_not_load_asyncio() -> None:
    """The migration path is synchronous, so no async runtime may be pulled in."""

    _assert_clean_exit(
        f"import sys, {MIGRATE_MODULE}; "
        "assert 'asyncio' not in sys.modules, 'migration module imported asyncio'"
    )


def test_public_migration_callables_are_synchronous() -> None:
    """No exported callable may be a coroutine or async-generator function."""

    _assert_clean_exit(
        f"import inspect, importlib; module = importlib.import_module({MIGRATE_MODULE!r}); "
        "asynchronous = sorted( "
        "name for name in dir(module) if not name.startswith('_') "
        "and (inspect.iscoroutinefunction(getattr(module, name)) "
        "or inspect.isasyncgenfunction(getattr(module, name))) "
        "); "
        "assert not asynchronous, f'async public callables: {asynchronous}'"
    )
