"""Live C46 acceptance scenarios for the PostgreSQL instance registry."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("psycopg", reason="C46 requires invocation-scoped Psycopg")

from postgres_test_database import (  # type: ignore[import-not-found]
    PostgresTestDatabase,
    isolated_database,
)
from test_real_postgres_acceptance import (  # type: ignore[import-not-found]
    assert_registry_shape,
    create_safe_registry,
    create_unsafe_registry,
    fresh_record,
    relation_exists,
    run_concurrent_migrations,
    run_locked_migration,
    run_registry,
)

from odoo_forge_instances_postgres.migrate import (
    RegistryTableRejectedError,
)
from odoo_forge_instances_postgres.real_postgres import CleanupReport

pytestmark = [pytest.mark.integration, pytest.mark.real_docker]


@pytest.fixture()
def database() -> Iterator[PostgresTestDatabase]:
    with isolated_database() as database:
        yield database


def test_fresh_catalog_migration(database: PostgresTestDatabase) -> None:
    run_registry(database)
    record = fresh_record("fresh")
    assert database.registry.store(record) == record
    assert database.registry.get(record.pointer) == record
    assert database.registry.list(record.pointer.scope) == (record,)
    assert_registry_shape(database)


def test_existing_safe_catalog_migration(database: PostgresTestDatabase) -> None:
    create_safe_registry(database)
    run_registry(database)
    assert_registry_shape(database)


def test_unsafe_catalog_is_rejected_and_rolled_back(database: PostgresTestDatabase) -> None:
    create_unsafe_registry(database)
    with pytest.raises(RegistryTableRejectedError, match="unlogged table"):
        run_registry(database)
    assert_registry_shape(database, expected_columns=("id",), expected_persistence="u")


def test_concurrent_migration_runners_serialize(database: PostgresTestDatabase) -> None:
    outcomes = run_concurrent_migrations(database)
    assert outcomes == (None, None)
    assert_registry_shape(database)


def test_external_ddl_lock_timeout_is_typed_and_bounded(database: PostgresTestDatabase) -> None:
    run_registry(database)
    run_locked_migration(database)
    assert_registry_shape(database)


def test_failure_rolls_back_transactional_work(database: PostgresTestDatabase) -> None:
    with database.connect() as connection:
        with pytest.raises(RuntimeError, match="scoped acceptance operation failed"):
            connection.execute("CREATE TABLE public.rollback_probe (id integer)")
            raise RuntimeError("scoped acceptance operation failed")
        connection.rollback()
    assert not relation_exists(database, "public.rollback_probe")


def test_repeated_migration_is_idempotent(database: PostgresTestDatabase) -> None:
    run_registry(database)
    run_registry(database)
    assert_registry_shape(database)


def test_success_and_failure_runs_clean_up_owned_resources() -> None:
    with isolated_database() as successful:
        run_registry(successful)
    assert successful.cleanup_report == CleanupReport()
    assert successful.clean

    with pytest.raises(RegistryTableRejectedError), isolated_database() as failing:
        create_unsafe_registry(failing)
        run_registry(failing)
    assert failing.cleanup_report == CleanupReport()
    assert failing.clean
