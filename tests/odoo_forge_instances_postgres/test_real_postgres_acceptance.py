"""Non-collected database and bounded-concurrency acceptance helpers."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from threading import Barrier, Event, Lock, Thread

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
    futures: tuple[Future[object], ...] = tuple(Future() for _ in workers)
    lock = Lock()

    def execute(index: int) -> None:
        try:
            value = workers[index]()
        except BaseException as error:
            with lock:
                futures[index].set_exception(error)
        else:
            with lock:
                futures[index].set_result(value)

    threads = [Thread(target=execute, args=(index,)) for index in range(len(workers))]
    for thread in threads:
        thread.start()
    try:
        values = tuple(future.result(timeout=12) for future in futures)
    finally:
        for thread in threads:
            thread.join(timeout=12)
    assert all(not thread.is_alive() for thread in threads)
    return values


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

    holder: Future[object] = Future()
    lock = Lock()

    def run_holder() -> None:
        try:
            hold_lock()
        except BaseException as error:
            with lock:
                holder.set_exception(error)
        else:
            with lock:
                holder.set_result(None)

    thread = Thread(target=run_holder)
    thread.start()
    try:
        assert acquired.wait(timeout=5)
        with database.connect() as connection, pytest.raises(MigrationLockTimeoutError):
            try:
                run_migration(connection)
            except MigrationLockTimeoutError:
                assert connection.info.transaction_status is TransactionStatus.IDLE
                raise
    finally:
        release.set()
        thread.join(timeout=12)
    assert not thread.is_alive()
    holder.result(timeout=1)


def relation_exists(database: PostgresTestDatabase, relation: str) -> bool:
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (relation,))
        row = cursor.fetchone()
    return row is not None and row[0] is not None
