from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("psycopg", reason="rollback verification requires PostgreSQL")

from postgres_test_database import (  # type: ignore[import-not-found]
    PostgresTestDatabase,
    isolated_database,
)

from odoo_forge.instance_registry import InstanceId, InstancePointer
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_instances_postgres.migrate import RegistryTableRejectedError, run_migration

pytestmark = [pytest.mark.integration, pytest.mark.real_docker]


def _pointer() -> InstancePointer:
    return InstancePointer(
        scope=ProjectScope(tenant=TenantId(value="legacy-tenant"), project_id="legacy-project"),
        instance_id=InstanceId(value="legacy-instance"),
    )


@pytest.fixture()
def database() -> Iterator[PostgresTestDatabase]:
    with isolated_database() as database:
        yield database


def _create_legacy_type_drift_table(database: PostgresTestDatabase) -> None:
    pointer = _pointer()
    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE public.instance_registry ("
            "tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, instance_id TEXT NOT NULL, "
            "resource_identifier TEXT NOT NULL, resource_kind TEXT NOT NULL, "
            "resource_ownership TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), operation_id INTEGER, "
            "request_digest TEXT, owned_resource_ids TEXT[], live_proof_expected BOOLEAN, "
            "PRIMARY KEY (tenant_id, project_id, instance_id))"
        )
        cursor.execute(
            "INSERT INTO public.instance_registry "
            "(tenant_id, project_id, instance_id, resource_identifier, resource_kind, "
            "resource_ownership) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                pointer.scope.tenant.value,
                pointer.scope.project_id,
                pointer.instance_id.value,
                "legacy-resource",
                "instance",
                "created",
            ),
        )


def test_wrong_legacy_operation_id_type_is_rejected_without_data_loss(
    database: PostgresTestDatabase,
) -> None:
    _create_legacy_type_drift_table(database)

    with (
        database.connect() as connection,
        pytest.raises(RegistryTableRejectedError, match="operation_id"),
    ):
        run_migration(connection)

    with database.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'instance_registry' "
            "AND a.attname = 'operation_id'"
        )
        assert cursor.fetchone() == ("integer",)

    legacy = database.registry.get(_pointer())
    assert legacy.receipt is None
