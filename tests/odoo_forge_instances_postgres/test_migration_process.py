"""Process-level import-purity and sync-only contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def test_environment_migration_order_survives_a_fresh_process() -> None:
    """The migration boundary keeps lock, DDL, catalog, and commit ordered."""
    result = _run(
        """
import json
from odoo_forge_instances_postgres.migrate import (
    _AUTHORITY_SIGNATURES,
    run_environment_migration,
)

events = []
rows = []
for table, signature in _AUTHORITY_SIGNATURES.items():
    for item in signature.split(';'):
        _, column, postgres_type, not_null, primary_key_order = item.split('|')
        rows.append((table, 'r', column, postgres_type, not_null == 'True', int(primary_key_order)))

class Cursor:
    def __init__(self, rows): self.rows = rows
    def execute(self, statement):
        upper = statement.upper()
        events.append(
            'lock-timeout' if 'LOCK_TIMEOUT' in upper else
            'advisory-lock' if 'PG_ADVISORY_XACT_LOCK' in upper else
            'ddl' if 'CREATE TABLE' in upper else
            'catalog' if 'PG_CATALOG.PG_CLASS' in upper else 'other'
        )
    def fetchall(self):
        return self.rows

class Connection:
    autocommit = False
    def __init__(self, rows): self._cursor = Cursor(rows)
    def cursor(self): return self._cursor
    def commit(self): events.append('commit')
    def rollback(self): events.append('rollback')

run_environment_migration(Connection(rows))
success = list(events)
events.clear()
try:
    run_environment_migration(Connection([]))
except Exception as error:
    events.append(type(error).__name__)
print(json.dumps({'success': success, 'refusal': events}))
"""
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "success": ["lock-timeout", "advisory-lock", "ddl", "catalog", "commit"],
        "refusal": [
            "lock-timeout",
            "advisory-lock",
            "ddl",
            "catalog",
            "rollback",
            "AuthorityTableRejectedError",
        ],
    }


def test_environment_refusal_and_recovery_order_survive_a_fresh_process() -> None:
    """Refusal and post-mutation recovery remain fail-closed across the boundary."""
    service_path = Path(__file__).resolve().parents[2] / "tests/data_environments/test_service.py"
    result = _run(
        f"""
import json
import runpy

module = runpy.run_path({str(service_path)!r})
events = []
refusal = module['service'](
    events, record=module['RECORD'].model_copy(update={{'receipt': None}}),
).run(module['request']())
refusal_events = list(events)

events.clear()
recovery = module['service'](
    events, coordinator=module['Coordinator'](events, RuntimeError())
).run(module['request']())
print(json.dumps({{'refusal': refusal_events, 'recovery': events}}))
assert refusal.outcome.failure_code.value == 'invalid_definition'
assert recovery.outcome.failure_code.value == 'mutation_failed'
"""
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "refusal": ["resolve", "instance"],
        "recovery": ["resolve", "instance", "policy", "acquire", "copy", "restore", "safe-state"],
    }
