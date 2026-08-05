"""Canonical data-environment definition authority port."""

from typing import Protocol, runtime_checkable

from odoo_forge.data_environments.types import DataEnvironmentDefinition


@runtime_checkable
class DataEnvironmentRegistry(Protocol):
    """Resolve definitions owned by the control plane, not repository config."""

    def resolve(self, environment_id: str) -> DataEnvironmentDefinition:
        """Return the authoritative definition for one opaque environment selector."""
        ...


__all__ = ["DataEnvironmentRegistry"]
