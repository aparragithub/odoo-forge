"""PostgreSQL adapter for scoped raw-data grants."""

from __future__ import annotations

from contextlib import suppress

from pydantic import ValidationError

from odoo_forge.data_environments.types import RawDataGrant
from odoo_forge.ports.raw_data_grant_authority import RawDataGrantAuthority

from .adapter import ConnectionAcquirer

__all__ = ["PostgresRawDataGrantAuthority"]

_AUTHORIZE_SQL = """
SELECT operation_id, environment_id, grantor, expires_at, reason, audit_reference
FROM public.raw_data_grants
WHERE operation_id = %s AND environment_id = %s
ORDER BY expires_at DESC
LIMIT 1
"""


class PostgresRawDataGrantAuthority(RawDataGrantAuthority):
    """Read one scoped grant and fail closed when its row is invalid."""

    def __init__(self, acquire: ConnectionAcquirer) -> None:
        self._acquire = acquire

    def authorize(self, operation_id: str, environment_id: str) -> RawDataGrant | None:
        with self._acquire() as connection:
            try:
                cursor = connection.cursor()
                cursor.execute(_AUTHORIZE_SQL, (operation_id, environment_id))
                row = cursor.fetchone()
                connection.commit()
            except Exception:
                with suppress(Exception):
                    connection.rollback()
                raise

        if row is None:
            return None
        try:
            return RawDataGrant.model_validate(
                {
                    "operation_id": row[0],
                    "environment_id": row[1],
                    "grantor": row[2],
                    "expires_at": row[3],
                    "reason": row[4],
                    "audit_reference": row[5],
                }
            )
        except (TypeError, ValueError, ValidationError):
            return None
