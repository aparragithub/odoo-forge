"""Behavioral contracts for the instance-registry migration."""

from __future__ import annotations

import importlib
import importlib.resources
import re

import pytest

from odoo_forge_instances_postgres.migrate import (
    CatalogVerificationError,
    MigrationAutocommitError,
    MigrationLockTimeoutError,
    RegistryTableRejectedError,
    run_migration,
)

ACCEPTING_ROW: tuple[object, ...] = (
    "r",
    "p",
    False,
    False,
    False,
    False,
    False,
    False,
    False,
    False,
)


class ScriptedLockTimeout(Exception):
    sqlstate = "55P03"


class FakeCursor:
    def __init__(
        self,
        catalog_row: tuple[object, ...] | None = ACCEPTING_ROW,
        relation_exists: bool | None = None,
        fail_on_contains: str | None = None,
        fail_exception: Exception | None = None,
    ) -> None:
        self.executed: list[str] = []
        self._catalog_row = catalog_row
        self._relation_exists = (
            catalog_row is not None if relation_exists is None else relation_exists
        )
        self._fail_on_contains, self._fail_exception = (
            fail_on_contains,
            fail_exception,
        )

    def execute(self, query: str) -> None:
        if self._fail_on_contains and self._fail_on_contains in query:
            assert self._fail_exception is not None
            raise self._fail_exception
        self.executed.append(query)

    def fetchone(self) -> tuple[object, ...] | None:
        if self.executed[-1].startswith("SELECT to_regclass"):
            return ("public.instance_registry",) if self._relation_exists else (None,)
        return self._catalog_row

    def fetchall(self) -> list[tuple[object, ...]]:
        return []


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
            "set_lock_timeout"
            if "LOCK_TIMEOUT" in upper
            else "advisory_lock"
            if "PG_ADVISORY_XACT_LOCK" in upper
            else "relation_exists"
            if "TO_REGCLASS" in upper
            else "create_table"
            if "CREATE TABLE" in upper
            else "table_lock"
            if "LOCK TABLE" in upper and "ACCESS EXCLUSIVE" in upper
            else "catalog_predicate"
            if "PG_CLASS" in upper
            else "unknown"
        )
    return kinds


def test_fresh_database_creates_and_verifies_an_ordinary_table() -> None:
    cursor = FakeCursor(relation_exists=False)
    conn = FakeConnection(cursor)
    run_migration(conn)
    assert _statement_kinds(cursor.executed) == [
        "set_lock_timeout",
        "advisory_lock",
        "relation_exists",
        "create_table",
        "table_lock",
        "catalog_predicate",
    ]
    assert conn.committed and not conn.rolled_back


def test_existing_table_is_locked_before_table_ddl() -> None:
    cursor = FakeCursor(relation_exists=True)
    conn = FakeConnection(cursor)

    run_migration(conn)

    assert _statement_kinds(cursor.executed) == [
        "set_lock_timeout",
        "advisory_lock",
        "relation_exists",
        "table_lock",
        "create_table",
        "catalog_predicate",
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


def test_catalog_signature_rejects_non_text_operation_id() -> None:
    row = (*ACCEPTING_ROW[:-1], True)
    with pytest.raises(RegistryTableRejectedError, match="operation_id"):
        run_migration(FakeConnection(FakeCursor(tuple(row))))


def test_catalog_signature_accepts_text_operation_id() -> None:
    connection = FakeConnection(FakeCursor(ACCEPTING_ROW))

    run_migration(connection)

    assert connection.committed and not connection.rolled_back


@pytest.mark.parametrize(
    ("field_index", "value", "variant_hint"),
    [
        (0, "p", "rejected variant: partitioned table"),
        (1, "u", "rejected variant: unlogged table"),
        (1, "t", "rejected variant: temporary table"),
        pytest.param(4, True, "rejected variant: table participates in inheritance", id="inherit"),
        (5, True, "rejected variant: non-constraint trigger present"),
        (6, True, "rejected variant: non-default rule present"),
        (7, True, "rejected variant: generated column present"),
        (8, True, "rejected variant: identity column present"),
    ],
)
def test_catalog_signature_rejects_unsafe_variant(
    field_index: int, value: object, variant_hint: str
) -> None:
    row = list(ACCEPTING_ROW)
    row[field_index] = value
    with pytest.raises(RegistryTableRejectedError) as excinfo:
        run_migration(FakeConnection(FakeCursor(tuple(row))))
    assert str(excinfo.value) == variant_hint


@pytest.mark.parametrize("field_index", [2, 3])
def test_row_level_security_rejected_unconditionally(field_index: int) -> None:
    row = list(ACCEPTING_ROW)
    row[field_index] = True
    with pytest.raises(RegistryTableRejectedError) as excinfo:
        run_migration(FakeConnection(FakeCursor(tuple(row))))
    assert str(excinfo.value) == "rejected variant: row-level security enabled"


def test_autocommit_connection_is_rejected_before_any_statement() -> None:
    cursor = FakeCursor()
    with pytest.raises(MigrationAutocommitError) as excinfo:
        run_migration(FakeConnection(cursor, autocommit=True))
    assert cursor.executed == []
    assert str(excinfo.value) == "run_migration requires a connection with autocommit disabled"


@pytest.mark.parametrize("lock_statement", ["pg_advisory_xact_lock", "LOCK TABLE"])
def test_lock_timeout_rolls_back_and_raises_typed_error(lock_statement: str) -> None:
    cursor = FakeCursor(fail_on_contains=lock_statement, fail_exception=ScriptedLockTimeout())
    conn = FakeConnection(cursor)
    with pytest.raises(MigrationLockTimeoutError) as excinfo:
        run_migration(conn)
    assert conn.rolled_back and not conn.committed
    assert "catalog_predicate" not in _statement_kinds(cursor.executed)
    expected_statement = (
        "SELECT pg_advisory_xact_lock(1329876815, 1230128945)"
        if lock_statement == "pg_advisory_xact_lock"
        else "LOCK TABLE public.instance_registry IN ACCESS EXCLUSIVE MODE"
    )
    assert str(excinfo.value) == f"lock acquisition timed out after 5s: {expected_statement}"
    assert isinstance(excinfo.value.__cause__, ScriptedLockTimeout)


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
    with pytest.raises(CatalogVerificationError) as excinfo:
        run_migration(conn)
    assert conn.rolled_back
    assert str(excinfo.value) == "catalog verification found no matching relation"


DESTRUCTIVE_KEYWORDS = ("drop", "truncate", "delete")
REVERSAL_NAME_PATTERN = r"down|revert|rollback|undo|drop|teardown"


def _destructive_keywords(sql: str) -> list[str]:
    return [
        keyword
        for keyword in DESTRUCTIVE_KEYWORDS
        if re.search(rf"\b{keyword}\b", sql, re.IGNORECASE)
    ]


@pytest.mark.parametrize("relation_exists", [False, True])
def test_migration_sends_no_destructive_statement(relation_exists: bool) -> None:
    """Neither the fresh nor the existing-table path may reach the database
    with a destructive statement."""

    cursor = FakeCursor(relation_exists=relation_exists)
    run_migration(FakeConnection(cursor))
    offenders = {
        statement: found
        for statement in cursor.executed
        if (found := _destructive_keywords(statement))
    }
    assert not offenders


def test_shipped_migration_sql_is_non_destructive() -> None:
    """The packaged DDL that ships to users must be additive only."""

    sql = (
        importlib.resources.files("odoo_forge_instances_postgres.migrations")
        .joinpath("0001_instance_registry.sql")
        .read_text(encoding="utf-8")
    )
    assert not _destructive_keywords(sql)


def test_shipped_migration_sql_adds_nullable_receipt_columns_and_unique_operation_index() -> None:
    """Lineage evidence is additive: nullable columns plus a partial unique index."""

    sql = (
        importlib.resources.files("odoo_forge_instances_postgres.migrations")
        .joinpath("0001_instance_registry.sql")
        .read_text(encoding="utf-8")
    )
    upper = sql.upper()
    for column in ("OPERATION_ID", "REQUEST_DIGEST", "OWNED_RESOURCE_IDS", "LIVE_PROOF_EXPECTED"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in upper
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in upper
    assert "ON PUBLIC.INSTANCE_REGISTRY (OPERATION_ID)" in upper
    assert "WHERE OPERATION_ID IS NOT NULL" in upper
    assert not _destructive_keywords(sql)


def test_public_surface_exposes_no_reversal_entry_point() -> None:
    """The module exports the forward migration and no way to reverse it."""

    module = importlib.import_module("odoo_forge_instances_postgres.migrate")
    public_callables = {
        name for name in dir(module) if not name.startswith("_") and callable(getattr(module, name))
    }
    assert "run_migration" in public_callables
    assert not {
        name for name in public_callables if re.search(REVERSAL_NAME_PATTERN, name, re.IGNORECASE)
    }
