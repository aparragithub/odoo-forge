"""Provider-neutral instance state registry domain contract."""

from odoo_forge.instance_registry.errors import InstanceRecordNotFoundError, InstanceRegistryError
from odoo_forge.instance_registry.types import InstanceId, InstancePointer, InstanceRecord

__all__ = [
    "InstanceId",
    "InstancePointer",
    "InstanceRecord",
    "InstanceRecordNotFoundError",
    "InstanceRegistryError",
]
