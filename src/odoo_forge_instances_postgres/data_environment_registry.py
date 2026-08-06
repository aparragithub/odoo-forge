"""PostgreSQL adapter for canonical data-environment definitions."""

from __future__ import annotations

from contextlib import suppress

from pydantic import ValidationError

from odoo_forge.data_environments.errors import EnvironmentDefinitionUnavailableError
from odoo_forge.data_environments.types import DataEnvironmentDefinition
from odoo_forge.ports.data_environment_registry import DataEnvironmentRegistry

from .adapter import ConnectionAcquirer

__all__ = ["PostgresDataEnvironmentRegistry"]

_RESOLVE_SQL = """
SELECT environment_id, owner, tenant_id, project_id, lifecycle, policy_ref, relationships
FROM public.data_environment_registry
WHERE environment_id = %s
"""


class PostgresDataEnvironmentRegistry(DataEnvironmentRegistry):
    """Resolve canonical definitions without owning the shared connection pool."""

    def __init__(self, acquire: ConnectionAcquirer) -> None:
        self._acquire = acquire

    def resolve(self, environment_id: str) -> DataEnvironmentDefinition:
        with self._acquire() as connection:
            try:
                cursor = connection.cursor()
                cursor.execute(_RESOLVE_SQL, (environment_id,))
                row = cursor.fetchone()
                connection.commit()
            except Exception:
                with suppress(Exception):
                    connection.rollback()
                raise

        if row is None:
            raise EnvironmentDefinitionUnavailableError()
        try:
            return DataEnvironmentDefinition.model_validate(
                {
                    "environment_id": row[0],
                    "owner": row[1],
                    "scope": {
                        "tenant": {"value": row[2]},
                        "project_id": row[3],
                    },
                    "lifecycle": row[4],
                    "policy_ref": row[5],
                    "relationships": row[6] or (),
                }
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise EnvironmentDefinitionUnavailableError() from exc
