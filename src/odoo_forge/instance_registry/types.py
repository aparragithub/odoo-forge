"""Provider-neutral, immutable values for the instance state registry."""

from pydantic import BaseModel, ConfigDict, Field

from odoo_forge.resource_ownership.types import OwnershipReceipt, ResourceRef
from odoo_forge.tenancy.types import ProjectScope


class _InstanceRegistryValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class InstanceId(_InstanceRegistryValue):
    """Opaque, non-empty identity for one managed instance."""

    value: str = Field(min_length=1)


class InstancePointer(_InstanceRegistryValue):
    """Provider-neutral instance identity scoped to one project."""

    scope: ProjectScope
    instance_id: InstanceId


class InstanceRecord(_InstanceRegistryValue):
    """Immutable control-plane metadata for one registered instance."""

    pointer: InstancePointer
    resource: ResourceRef
    receipt: OwnershipReceipt | None = None
    """Optional lineage evidence. Legacy rows have no receipt; a canonical
    authoritative registration (`InstanceRegistry.register`) requires one."""


__all__ = ["InstanceId", "InstancePointer", "InstanceRecord"]
