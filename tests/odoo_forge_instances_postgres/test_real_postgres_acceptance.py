"""Non-collected database and bounded-concurrency acceptance helpers."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

pytest.importorskip("psycopg", reason="C46 requires invocation-scoped Psycopg")

from postgres_test_database import PostgresTestDatabase  # type: ignore[import-not-found]
from psycopg.pq import TransactionStatus  # type: ignore[import-not-found]

from odoo_forge.instance_registry import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.resource_ownership import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_instances_postgres.migrate import (
    MigrationLockTimeoutError,
    run_migration,
)

DEFAULT_COLUMNS = (
    "tenant_id",
    "project_id",
    "instance_id",
    "resource_identifier",
    "resource_kind",
    "resource_ownership",
    "created_at",
    "updated_at",
)


def fresh_record(instance: str) -> InstanceRecord:
    return InstanceRecord(
        pointer=InstancePointer(
            scope=ProjectScope(tenant=TenantId(value="tenant-live"), project_id="project-live"),
            instance_id=InstanceId(value=instance),
        ),
        resource=ResourceRef(
            identifier=f"resource-{instance}",
            resource_kind="instance",
            ownership=ResourceOwnership.CREATED,
        ),
    )


def run_registry(database: PostgresTestDatabase) -> None:
    with database.connect() as connection:
        run_migration(connection)


def assert_registry_shape(
    database: PostgresTestDatabase,
    *,
    expected_columns: tuple[str, ...] = DEFAULT_COLUMNS,
    expected_persistence: str = "p",
) -> None:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'instance_registry' "
            "ORDER BY ordinal_position"
        )
        columns = tuple(row[0] for row in cursor.fetchall())
        cursor.execute(
            "SELECT relkind, relpersistence FROM pg_catalog.pg_class "
            "WHERE oid = 'public.instance_registry'::regclass"
        )
        relation = cursor.fetchone()
    assert columns == expected_columns
    assert relation == ("r", expected_persistence)


def create_safe_registry(database: PostgresTestDatabase) -> None:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE public.instance_registry ("
            "tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, instance_id TEXT NOT NULL, "
            "resource_identifier TEXT NOT NULL, resource_kind TEXT NOT NULL, "
            "resource_ownership TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "PRIMARY KEY (tenant_id, project_id, instance_id))"
        )


def create_unsafe_registry(database: PostgresTestDatabase) -> None:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute("CREATE UNLOGGED TABLE public.instance_registry (id integer NOT NULL)")


def _bounded_threads(workers: tuple[Callable[[], object], ...]) -> tuple[object, ...]:
    with ThreadPoolExecutor(max_workers=len(workers)) as executor:
        futures = tuple(executor.submit(worker) for worker in workers)
        return tuple(future.result(timeout=12) for future in futures)


def run_concurrent_migrations(database: PostgresTestDatabase) -> tuple[object, ...]:
    barrier = Barrier(2)

    def worker() -> None:
        barrier.wait(timeout=10)
        run_registry(database)

    return _bounded_threads((worker, worker))


def run_locked_migration(database: PostgresTestDatabase) -> None:
    acquired = Event()
    release = Event()

    def hold_lock() -> None:
        with database.connect() as connection, connection.cursor() as cursor:
            cursor.execute("LOCK TABLE public.instance_registry IN ACCESS EXCLUSIVE MODE")
            acquired.set()
            if not release.wait(timeout=12):
                raise TimeoutError("bounded DDL lock holder did not receive release")

    with ThreadPoolExecutor(max_workers=1) as executor:
        holder = executor.submit(hold_lock)
        main_error: BaseException | None = None
        try:
            assert acquired.wait(timeout=5)
            with database.connect() as connection, pytest.raises(MigrationLockTimeoutError):
                try:
                    run_migration(connection)
                except MigrationLockTimeoutError:
                    assert connection.info.transaction_status is TransactionStatus.IDLE
                    raise
        except BaseException as error:
            main_error = error
            raise
        finally:
            release.set()
            try:
                holder.result(timeout=12)
            except BaseException as holder_error:
                if main_error is not None:
                    raise BaseExceptionGroup(
                        "migration assertion and lock holder both failed",
                        (main_error, holder_error),
                    ) from None
                raise


def relation_exists(database: PostgresTestDatabase, relation: str) -> bool:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (relation,))
        row = cursor.fetchone()
    return row is not None and row[0] is not None
