"""Contracts for the separate data-environment PostgreSQL authorities."""

from __future__ import annotations

import importlib.resources
from contextlib import AbstractContextManager
from datetime import UTC, datetime

import pytest
from postgres_test_database import (  # type: ignore[import-not-found]
    isolated_database,
)
from test_real_postgres_acceptance import fresh_record  # type: ignore[import-not-found]

from odoo_forge.data_environments.errors import EnvironmentDefinitionUnavailableError
from odoo_forge.data_environments.types import (
    DataEnvironmentDefinition,
    RawDataGrant,
)
from odoo_forge.ports.data_environment_registry import DataEnvironmentRegistry
from odoo_forge.ports.raw_data_grant_authority import RawDataGrantAuthority
from odoo_forge_instances_postgres.data_environment_registry import (
    PostgresDataEnvironmentRegistry,
)
from odoo_forge_instances_postgres.migrate import run_environment_migration, run_migration
from odoo_forge_instances_postgres.raw_data_grant_authority import (
    PostgresRawDataGrantAuthority,
)


class _Cursor:
    def __init__(self, row: tuple[object, ...] | None, *, fail: bool = False) -> None:
        self.row = row
        self.fail = fail
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> object:
        if self.fail:
            raise RuntimeError("scripted migration failure")
        self.queries.append((query, parameters))
        return None

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[object, ...]]:
        return []


class _Connection:
    def __init__(self, row: tuple[object, ...] | None, *, cursor_fails: bool = False) -> None:
        self.cursor_instance = _Cursor(row, fail=cursor_fails)
        self.autocommit = False
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.calls = 0

    def __call__(self) -> AbstractContextManager[_Connection]:
        self.calls += 1
        return _ConnectionContext(self.connection)


class _ConnectionContext(AbstractContextManager[_Connection]):
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, *_: object) -> None:
        return None


def test_authorities_are_separate_runtime_protocols_and_share_only_acquirer() -> None:
    connection = _Connection(None)
    acquire = _Acquire(connection)

    registry = PostgresDataEnvironmentRegistry(acquire)
    grants = PostgresRawDataGrantAuthority(acquire)

    assert isinstance(registry, DataEnvironmentRegistry)
    assert isinstance(grants, RawDataGrantAuthority)
    assert not isinstance(registry, RawDataGrantAuthority)
    assert not isinstance(grants, DataEnvironmentRegistry)
    assert acquire.calls == 0


def test_registry_reads_only_its_owned_table_and_rehydrates_definition() -> None:
    row = (
        "qa",
        "platform",
        "tenant-1",
        "project-1",
        "active",
        "policy-qa",
        [{"source_environment_id": "production", "target_environment_id": "qa"}],
    )
    connection = _Connection(row)
    acquire = _Acquire(connection)

    definition = PostgresDataEnvironmentRegistry(acquire).resolve("qa")

    assert definition == DataEnvironmentDefinition.model_validate(
        {
            "environment_id": "qa",
            "owner": "platform",
            "scope": {"tenant": {"value": "tenant-1"}, "project_id": "project-1"},
            "lifecycle": "active",
            "policy_ref": "policy-qa",
            "relationships": row[6],
        }
    )
    assert acquire.calls == 1
    assert connection.cursor_instance.queries[0][0].count("data_environment_registry") == 1


def test_registry_missing_definition_fails_closed() -> None:
    with pytest.raises(EnvironmentDefinitionUnavailableError):
        PostgresDataEnvironmentRegistry(_Acquire(_Connection(None))).resolve("missing")


def test_grant_authority_reads_only_scoped_grants_and_rehydrates_grant() -> None:
    expires_at = datetime(2030, 1, 1, tzinfo=UTC)
    row = ("refresh-42", "qa", "operator-1", expires_at, "approved refresh", "audit-42")
    connection = _Connection(row)

    grant = PostgresRawDataGrantAuthority(_Acquire(connection)).authorize("refresh-42", "qa")

    assert grant == RawDataGrant(
        operation_id="refresh-42",
        environment_id="qa",
        grantor="operator-1",
        expires_at=expires_at,
        reason="approved refresh",
        audit_reference="audit-42",
    )
    assert connection.cursor_instance.queries[0][0].count("raw_data_grants") == 1


def test_invalid_grant_fails_closed() -> None:
    invalid = ("refresh-42", "qa", "operator-1", datetime(2030, 1, 1), "approved", "audit-42")

    assert (
        PostgresRawDataGrantAuthority(_Acquire(_Connection(invalid))).authorize("refresh-42", "qa")
        is None
    )


def test_environment_migration_is_additive_and_owns_exactly_two_tables() -> None:
    sql = (
        importlib.resources.files("odoo_forge_instances_postgres.migrations")
        .joinpath("0002_data_environments.sql")
        .read_text(encoding="utf-8")
    )
    upper = sql.upper()

    assert upper.count("CREATE TABLE") == 2
    assert "DATA_ENVIRONMENT_REGISTRY" in upper
    assert "RAW_DATA_GRANTS" in upper
    assert "INSTANCE_REGISTRY" not in upper
    assert not any(keyword in upper for keyword in ("DROP ", "TRUNCATE ", "DELETE ", "ALTER "))


def test_environment_migration_uses_one_bounded_transaction() -> None:
    connection = _Connection(None)

    run_environment_migration(connection)

    assert connection.committed
    assert not connection.rolled_back
    assert len(connection.cursor_instance.queries) == 1


def test_environment_migration_rolls_back_when_ddl_fails() -> None:
    connection = _Connection(None, cursor_fails=True)

    with pytest.raises(RuntimeError, match="scripted migration failure"):
        run_environment_migration(connection)

    assert connection.rolled_back
    assert not connection.committed


@pytest.mark.integration
@pytest.mark.real_docker
def test_environment_migration_preserves_instance_registry_schema_and_data() -> None:
    with isolated_database() as database:
        with database.connect() as connection:
            run_migration(connection)
            record = fresh_record("slice-2")
            database.registry.store(record)
            cursor = connection.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'instance_registry' ORDER BY ordinal_position",
                (),
            )
            before = tuple(row[0] for row in cursor.fetchall())

        with database.connect() as connection:
            run_environment_migration(connection)
            cursor = connection.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'instance_registry' ORDER BY ordinal_position",
                (),
            )
            after = tuple(row[0] for row in cursor.fetchall())

        assert before == after
        assert database.registry.get(record.pointer) == record
