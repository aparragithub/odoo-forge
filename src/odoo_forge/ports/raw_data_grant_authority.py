"""Separate raw-data exception authority port."""

from typing import Protocol, runtime_checkable

from odoo_forge.data_environments.types import RawDataGrant


@runtime_checkable
class RawDataGrantAuthority(Protocol):
    """Authorize raw data independently from custody or environment definition."""

    def authorize(self, operation_id: str, environment_id: str) -> RawDataGrant | None:
        """Return a scoped grant, or None so callers fail closed."""
        ...


__all__ = ["RawDataGrantAuthority"]
