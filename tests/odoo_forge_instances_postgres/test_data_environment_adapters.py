"""Contracts for the separate data-environment PostgreSQL authorities."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime

import pytest
from postgres_test_database import (  # type: ignore[import-not-found]
    PostgresTestDatabase,
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
from odoo_forge_instances_postgres.migrate import (
    AuthorityTableRejectedError,
    run_environment_migration,
    run_migration,
)
from odoo_forge_instances_postgres.raw_data_grant_authority import (
    PostgresRawDataGrantAuthority,
)


@pytest.fixture()
def database() -> Iterator[PostgresTestDatabase]:
    with isolated_database() as database:
        yield database


class _Cursor:
    def __init__(
        self,
        row: tuple[object, ...] | None,
        *,
        authority_rows: tuple[tuple[object, ...], ...] = (),
        fail: bool = False,
    ) -> None:
        self.row = row
        self.authority_rows = authority_rows
        self.fail = fail

    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> object:
        if self.fail:
            raise RuntimeError("scripted migration failure")
        return None

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.authority_rows)


class _Connection:
    def __init__(
        self,
        row: tuple[object, ...] | None,
        *,
        authority_rows: tuple[tuple[object, ...], ...] = (),
        cursor_fails: bool = False,
    ) -> None:
        self.cursor_instance = _Cursor(row, authority_rows=authority_rows, fail=cursor_fails)
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


def test_invalid_grant_fails_closed() -> None:
    invalid = ("refresh-42", "qa", "operator-1", datetime(2030, 1, 1), "approved", "audit-42")

    assert (
        PostgresRawDataGrantAuthority(_Acquire(_Connection(invalid))).authorize("refresh-42", "qa")
        is None
    )


def _compatible_rows(table: str, signature: str) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (table, "r", column, postgres_type, True, int(primary_key_order))
        for column, postgres_type, primary_key_order in (
            item.split("|") for item in signature.split(";")
        )
    )


_COMPATIBLE_AUTHORITY_ROWS = _compatible_rows(
    "data_environment_registry",
    "environment_id|text|1;owner|text|0;tenant_id|text|0;project_id|text|0;lifecycle|text|0;policy_ref|text|0;relationships|jsonb|0",
) + _compatible_rows(
    "raw_data_grants",
    "operation_id|text|1;environment_id|text|2;grantor|text|0;expires_at|timestamp with time zone|0;reason|text|0;audit_reference|text|0",  # noqa: E501
)


def test_environment_migration_uses_one_bounded_transaction() -> None:
    connection = _Connection(None, authority_rows=_COMPATIBLE_AUTHORITY_ROWS)

    run_environment_migration(connection)

    assert connection.committed
    assert not connection.rolled_back


def test_environment_migration_rolls_back_when_ddl_fails() -> None:
    connection = _Connection(None, cursor_fails=True)

    with pytest.raises(RuntimeError, match="scripted migration failure"):
        run_environment_migration(connection)

    assert connection.rolled_back
    assert not connection.committed


def _authority_catalog(database: PostgresTestDatabase) -> tuple[tuple[object, ...], ...]:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname, c.relkind, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, COALESCE(pk.ordinality, 0) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped LEFT JOIN LATERAL (SELECT key.ordinality FROM pg_catalog.pg_constraint con CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY key(attnum, ordinality) WHERE con.conrelid = c.oid AND con.contype = 'p' AND key.attnum = a.attnum) pk ON TRUE WHERE n.nspname = 'public' AND c.relname IN ('data_environment_registry', 'raw_data_grants') ORDER BY c.relname, a.attnum"  # noqa: E501
        )
        return tuple(cursor.fetchall())


@pytest.mark.integration
@pytest.mark.real_docker
def test_environment_migration_creates_exact_authority_catalog(
    database: PostgresTestDatabase,
) -> None:
    with database.connect() as connection:
        run_environment_migration(connection)

    assert _authority_catalog(database) == _COMPATIBLE_AUTHORITY_ROWS
    with database.connect() as connection:
        run_environment_migration(connection)
    assert _authority_catalog(database) == _COMPATIBLE_AUTHORITY_ROWS


@pytest.mark.integration
@pytest.mark.real_docker
def test_incompatible_existing_authority_table_rolls_back(
    database: PostgresTestDatabase,
) -> None:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE public.data_environment_registry (environment_id TEXT PRIMARY KEY, "
            "owner TEXT NOT NULL, tenant_id INTEGER NOT NULL, project_id TEXT NOT NULL, "
            "lifecycle TEXT NOT NULL, policy_ref TEXT NOT NULL, relationships JSONB NOT NULL)"
        )

    with database.connect() as connection, pytest.raises(AuthorityTableRejectedError, match="data_environment_registry"):  # fmt: skip  # noqa: E501
        run_environment_migration(connection)

    catalog = _authority_catalog(database)
    assert {row[0] for row in catalog} == {"data_environment_registry"}
    assert next(row[3] for row in catalog if row[2] == "tenant_id") == "integer"


@pytest.mark.integration
@pytest.mark.real_docker
def test_adapters_read_persisted_authority_records(database: PostgresTestDatabase) -> None:
    expires_at = datetime(2030, 1, 1, tzinfo=UTC)
    with database.connect() as connection, connection.cursor() as cursor:
        run_environment_migration(connection)
        # Keep the persisted JSON fixture readable as one observable record.
        # fmt: off
        cursor.execute(  # fmt: skip
            "INSERT INTO public.data_environment_registry VALUES "
            "(%s, %s, %s, %s, %s, %s, %s)",
            ("qa", "platform", "tenant-1", "project-1", "active", "policy-qa", '[{"source_environment_id":"production","target_environment_id":"qa"}]'),  # noqa: E501
        )
        # fmt: on
        cursor.execute(
            "INSERT INTO public.raw_data_grants VALUES (%s, %s, %s, %s, %s, %s)",
            ("refresh-42", "qa", "operator-1", expires_at, "approved refresh", "audit-42"),
        )
        connection.commit()

    definition = PostgresDataEnvironmentRegistry(database.acquire).resolve("qa")
    grant = PostgresRawDataGrantAuthority(database.acquire).authorize("refresh-42", "qa")

    assert (definition.environment_id, definition.owner, definition.policy_ref) == (
        "qa",
        "platform",
        "policy-qa",
    )
    assert definition.relationships[0].target_environment_id == "qa"
    assert grant == RawDataGrant(operation_id="refresh-42", environment_id="qa", grantor="operator-1", expires_at=expires_at, reason="approved refresh", audit_reference="audit-42")  # fmt: skip  # noqa: E501


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
