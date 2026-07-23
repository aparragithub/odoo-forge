"""Provider-neutral tenancy contract: canonical value types and typed error hierarchy."""

from odoo_forge.tenancy.errors import (
    CrossTenantAccessError,
    ProjectWithoutTenantError,
    QuotaExceededError,
    TenancyError,
    UnknownTenantError,
)
from odoo_forge.tenancy.types import ProjectScope, QuotaAuthority, TenantId, TenantScopedOwnership

__all__ = [
    "CrossTenantAccessError",
    "ProjectScope",
    "ProjectWithoutTenantError",
    "QuotaAuthority",
    "QuotaExceededError",
    "TenancyError",
    "TenantId",
    "TenantScopedOwnership",
    "UnknownTenantError",
]
