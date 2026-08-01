"""Behavioral contracts for the instance-registry migration."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import odoo_forge_instances_postgres.migrate as migrate_module
from odoo_forge_instances_postgres.migrate import (
    CatalogVerificationError,
    MigrationAutocommitError,
    MigrationLockTimeoutError,
    RegistryTableRejectedError,
    run_migration,
)

ACCEPTING_ROW: tuple[object, ...] = ("r", "p", False, False, False, False, False, False, False)


class ScriptedLockTimeout(Exception):
    sqlstate = "55P03"


class FakeCursor:
    def __init__(
        self,
        catalog_row: tuple[object, ...] | None = ACCEPTING_ROW,
        fail_on_contains: str | None = None,
        fail_exception: Exception | None = None,
    ) -> None:
        self.executed: list[str] = []
        self._catalog_row, self._fail_on_contains, self._fail_exception = (
            catalog_row,
            fail_on_contains,
            fail_exception,
        )

    def execute(self, query: str) -> None:
        if self._fail_on_contains and self._fail_on_contains in query:
            assert self._fail_exception is not None
            raise self._fail_exception
        self.executed.append(query)
    def fetchone(self) -> tuple[object, ...] | None:
        return self._catalog_row


class FakeConnection:
    def __init__(self, cursor: FakeCursor, autocommit: bool = False) -> None:
        self.autocommit, self._cursor = autocommit, cursor
        self.committed = self.rolled_back = False
    def cursor(self) -> FakeCursor:
        return self._cursor
    def commit(self) -> None:
        self.committed = True
    def rollback(self) -> None:
        self.rolled_back = True


def _statement_kinds(executed: list[str]) -> list[str]:
    kinds = []
    for statement in executed:
        upper = statement.upper()
        kinds.append(
            "set_lock_timeout" if "LOCK_TIMEOUT" in upper else
            "advisory_lock" if "PG_ADVISORY_XACT_LOCK" in upper else
            "create_table" if "CREATE TABLE" in upper else
            "table_lock" if "LOCK TABLE" in upper and "ACCESS EXCLUSIVE" in upper else
            "catalog_predicate" if "PG_CLASS" in upper else "unknown"
        )
    return kinds


def test_fresh_database_creates_and_verifies_an_ordinary_table() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    run_migration(conn)
    assert _statement_kinds(cursor.executed) == [
        "set_lock_timeout", "advisory_lock", "create_table", "table_lock", "catalog_predicate"
    ]
    assert conn.committed and not conn.rolled_back


def test_catalog_predicate_is_constant_and_ignores_dropped_columns() -> None:
    cursor = FakeCursor()
    run_migration(FakeConnection(cursor))
    predicate = cursor.executed[-1]
    assert "public.instance_registry" not in predicate
    assert "'public'" in predicate and "'instance_registry'" in predicate
    assert "i.inhrelid = c.oid OR i.inhparent = c.oid" in predicate
    assert "NOT a.attisdropped" in predicate


@pytest.mark.parametrize(
    ("field_index", "value", "variant_hint"),
    [
        (0, "p", "partition"), (1, "u", "unlogged"), (1, "t", "temporary"),
        pytest.param(4, True, "inherit", id="inherit-child"),
        pytest.param(4, True, "inherit", id="inherit-parent"),
        (5, True, "trigger"), (6, True, "rule"), (7, True, "generat"), (8, True, "identity"),
    ],
)
def test_catalog_signature_rejects_unsafe_variant(
    field_index: int, value: object, variant_hint: str
) -> None:
    row = list(ACCEPTING_ROW)
    row[field_index] = value
    with pytest.raises(RegistryTableRejectedError, match=variant_hint):
        run_migration(FakeConnection(FakeCursor(tuple(row))))


@pytest.mark.parametrize("field_index", [2, 3])
def test_row_level_security_rejected_unconditionally(field_index: int) -> None:
    row = list(ACCEPTING_ROW)
    row[field_index] = True
    with pytest.raises(RegistryTableRejectedError, match="row-level security"):
        run_migration(FakeConnection(FakeCursor(tuple(row))))


def test_autocommit_connection_is_rejected_before_any_statement() -> None:
    cursor = FakeCursor()
    with pytest.raises(MigrationAutocommitError):
        run_migration(FakeConnection(cursor, autocommit=True))
    assert cursor.executed == []


@pytest.mark.parametrize("lock_statement", ["pg_advisory_xact_lock", "LOCK TABLE"])
def test_lock_timeout_rolls_back_and_raises_typed_error(lock_statement: str) -> None:
    cursor = FakeCursor(fail_on_contains=lock_statement, fail_exception=ScriptedLockTimeout())
    conn = FakeConnection(cursor)
    with pytest.raises(MigrationLockTimeoutError):
        run_migration(conn)
    assert conn.rolled_back and not conn.committed
    assert "catalog_predicate" not in _statement_kinds(cursor.executed)


def test_repeated_runs_converge_without_error() -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    run_migration(conn)
    run_migration(conn)
    assert conn.committed and _statement_kinds(cursor.executed).count("create_table") == 2


def test_interrupted_run_is_safely_retryable() -> None:
    failed = FakeConnection(FakeCursor(fail_on_contains="pg_class", fail_exception=RuntimeError()))
    with pytest.raises(RuntimeError):
        run_migration(failed)
    assert failed.rolled_back and not failed.committed
    retry = FakeConnection(FakeCursor())
    run_migration(retry)
    assert retry.committed


def test_missing_relation_is_a_typed_verification_failure() -> None:
    conn = FakeConnection(FakeCursor(catalog_row=None))
    with pytest.raises(CatalogVerificationError, match="no matching relation"):
        run_migration(conn)
    assert conn.rolled_back


def test_no_drop_statement_and_no_down_migration_entry_point() -> None:
    migrate_source = inspect.getsource(migrate_module)
    sql_path = Path(__file__).parents[2] / (
        "src/odoo_forge_instances_postgres/migrations/0001_instance_registry.sql"
    )
    sql_source = sql_path.read_text(encoding="utf-8")
    assert not re.search(r"\bdrop\b", migrate_source + sql_source, re.IGNORECASE)
    assert not hasattr(migrate_module, "down_migration")
    assert not hasattr(migrate_module, "rollback_migration")
