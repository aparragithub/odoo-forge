"""Explicit, synchronous migration for the instance registry PostgreSQL schema.

This module MUST NOT be imported for its side effects: importing it performs
no database connection, lock acquisition, or schema change. Callers invoke
`run_migration(conn)` explicitly to apply the schema.
"""

from __future__ import annotations

import importlib.resources
from typing import Protocol

from .errors import (
    AuthorityTableRejectedError,
    CatalogVerificationError,
    MigrationAutocommitError,
    MigrationLockTimeoutError,
    RegistryTableRejectedError,
)

__all__ = [
    "MigrationAutocommitError",
    "MigrationLockTimeoutError",
    "RegistryTableRejectedError",
    "AuthorityTableRejectedError",
    "CatalogVerificationError",
    "run_migration",
    "run_environment_migration",
]

ADVISORY_LOCK_KEY_1 = 1329876815
ADVISORY_LOCK_KEY_2 = 1230128945
LOCK_TIMEOUT = "5s"

_REGISTRY_TABLE = "public.instance_registry"
_LOCK_TIMEOUT_SQLSTATE = "55P03"

_ADVISORY_LOCK_SQL = f"SELECT pg_advisory_xact_lock({ADVISORY_LOCK_KEY_1}, {ADVISORY_LOCK_KEY_2})"
_TABLE_EXISTS_SQL = "SELECT to_regclass('public.instance_registry')"
_TABLE_LOCK_SQL = f"LOCK TABLE {_REGISTRY_TABLE} IN ACCESS EXCLUSIVE MODE"
_CATALOG_PREDICATE_SQL = """
SELECT c.relkind, c.relpersistence, c.relrowsecurity, c.relforcerowsecurity,
  EXISTS(SELECT 1 FROM pg_catalog.pg_inherits i
         WHERE i.inhrelid = c.oid OR i.inhparent = c.oid)                    AS inherited,
  EXISTS(SELECT 1 FROM pg_catalog.pg_trigger t
         WHERE t.tgrelid = c.oid AND NOT (t.tgisinternal AND t.tgconstraint <> 0)) AS triggered,
  EXISTS(SELECT 1 FROM pg_catalog.pg_rewrite r
         WHERE r.ev_class = c.oid AND r.rulename <> '_RETURN')               AS ruled,
  EXISTS(SELECT 1 FROM pg_catalog.pg_attribute a WHERE a.attrelid = c.oid
         AND a.attnum > 0 AND NOT a.attisdropped AND a.attgenerated <> '')   AS generated,
  EXISTS(SELECT 1 FROM pg_catalog.pg_attribute a WHERE a.attrelid = c.oid
         AND a.attnum > 0 AND NOT a.attisdropped AND a.attidentity <> '')    AS identity,
  EXISTS(SELECT 1 FROM pg_catalog.pg_attribute a WHERE a.attrelid = c.oid
         AND a.attname = 'operation_id' AND a.attnum > 0 AND NOT a.attisdropped
         AND a.atttypid <> 'text'::regtype) AS operation_id_type_invalid
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'instance_registry';
"""
_AUTHORITY_CATALOG_SQL = """
SELECT c.relname, c.relkind, a.attname, format_type(a.atttypid, a.atttypmod),
  a.attnotnull, COALESCE(pk.ordinality, 0)
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
  AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN LATERAL (
  SELECT key.ordinality
  FROM pg_catalog.pg_constraint con
  CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY key(attnum, ordinality)
  WHERE con.conrelid = c.oid AND con.contype = 'p' AND key.attnum = a.attnum
) pk ON TRUE
WHERE n.nspname = 'public' AND c.relname IN
  ('data_environment_registry', 'raw_data_grants')
ORDER BY c.relname, a.attnum;
"""

_AUTHORITY_SIGNATURES = {
    "data_environment_registry": "r|environment_id|text|True|1;r|owner|text|True|0;r|tenant_id|text|True|0;r|project_id|text|True|0;r|lifecycle|text|True|0;r|policy_ref|text|True|0;r|relationships|jsonb|True|0",  # noqa: E501
    "raw_data_grants": "r|operation_id|text|True|1;r|environment_id|text|True|2;r|grantor|text|True|0;r|expires_at|timestamp with time zone|True|0;r|reason|text|True|0;r|audit_reference|text|True|0",  # noqa: E501
}


class Connection(Protocol):
    """Structural contract for the synchronous connection `run_migration` needs."""

    autocommit: bool

    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class Cursor(Protocol):
    """Structural contract for the synchronous cursor `run_migration` needs."""

    def execute(self, query: str) -> object: ...

    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


def _migration_sql() -> str:
    return (
        importlib.resources.files("odoo_forge_instances_postgres.migrations")
        .joinpath("0001_instance_registry.sql")
        .read_text(encoding="utf-8")
    )


def _environment_migration_sql() -> str:
    return (
        importlib.resources.files("odoo_forge_instances_postgres.migrations")
        .joinpath("0002_data_environments.sql")
        .read_text(encoding="utf-8")
    )


def _execute_guarding_timeout(cursor: Cursor, statement: str) -> None:
    try:
        cursor.execute(statement)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _LOCK_TIMEOUT_SQLSTATE:
            raise MigrationLockTimeoutError(
                f"lock acquisition timed out after {LOCK_TIMEOUT}: {statement}"
            ) from exc
        raise


def _verify_catalog_signature(row: tuple[object, ...] | None) -> None:
    if row is None:
        raise CatalogVerificationError("catalog verification found no matching relation")

    (
        relkind,
        relpersistence,
        rls,
        force_rls,
        inherited,
        triggered,
        ruled,
        generated,
        identity,
        operation_id_type_invalid,
    ) = row

    if relkind == "p":
        raise RegistryTableRejectedError("rejected variant: partitioned table")
    if relkind != "r":
        raise RegistryTableRejectedError(f"rejected variant: relkind={relkind!r} (not ordinary)")
    if relpersistence == "u":
        raise RegistryTableRejectedError("rejected variant: unlogged table")
    if relpersistence == "t":
        raise RegistryTableRejectedError("rejected variant: temporary table")
    if relpersistence != "p":
        raise RegistryTableRejectedError(
            f"rejected variant: relpersistence={relpersistence!r} (not ordinary)"
        )
    if rls or force_rls:
        raise RegistryTableRejectedError("rejected variant: row-level security enabled")
    if inherited:
        raise RegistryTableRejectedError("rejected variant: table participates in inheritance")
    if triggered:
        raise RegistryTableRejectedError("rejected variant: non-constraint trigger present")
    if ruled:
        raise RegistryTableRejectedError("rejected variant: non-default rule present")
    if generated:
        raise RegistryTableRejectedError("rejected variant: generated column present")
    if identity:
        raise RegistryTableRejectedError("rejected variant: identity column present")
    if operation_id_type_invalid:
        raise RegistryTableRejectedError("rejected schema: operation_id must have type text")


def _verify_authority_catalog(rows: list[tuple[object, ...]]) -> None:
    observed: dict[str, list[str]] = {}
    for row in rows:
        table, relkind, column, postgres_type, not_null, primary_key_order = row
        signature = "|".join(
            map(str, (relkind, column, postgres_type, not_null, primary_key_order))
        )
        observed.setdefault(str(table), []).append(signature)

    for table, expected in _AUTHORITY_SIGNATURES.items():
        if ";".join(observed.get(table, ())) != expected:
            raise AuthorityTableRejectedError(f"rejected schema: {table} is not exactly compatible")


def run_migration(conn: Connection) -> None:
    """Apply the instance registry schema, verifying it is safe to own.

    Raises a typed error naming the specific rejection reason on any
    catalog-signature violation, lock timeout, or autocommit misuse.
    """

    if conn.autocommit is not False:
        raise MigrationAutocommitError(
            "run_migration requires a connection with autocommit disabled"
        )

    cursor = conn.cursor()
    try:
        cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        _execute_guarding_timeout(cursor, _ADVISORY_LOCK_SQL)
        _execute_guarding_timeout(cursor, _TABLE_EXISTS_SQL)
        relation = cursor.fetchone()
        if relation is not None and relation[0] is not None:
            _execute_guarding_timeout(cursor, _TABLE_LOCK_SQL)
        cursor.execute(_migration_sql())
        if relation is None or relation[0] is None:
            _execute_guarding_timeout(cursor, _TABLE_LOCK_SQL)
        cursor.execute(_CATALOG_PREDICATE_SQL)
        _verify_catalog_signature(cursor.fetchone())
    except Exception:
        conn.rollback()
        raise

    conn.commit()


def run_environment_migration(conn: Connection) -> None:
    """Create only the two separately owned data-environment authority tables."""

    if conn.autocommit is not False:
        raise MigrationAutocommitError(
            "run_environment_migration requires a connection with autocommit disabled"
        )

    cursor = conn.cursor()
    try:
        cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        _execute_guarding_timeout(cursor, _ADVISORY_LOCK_SQL)
        _execute_guarding_timeout(cursor, _environment_migration_sql())
        cursor.execute(_AUTHORITY_CATALOG_SQL)
        _verify_authority_catalog(cursor.fetchall())
    except Exception:
        conn.rollback()
        raise
    conn.commit()
