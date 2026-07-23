"""Canonical, provider-neutral tenancy values.

This module is the platform-scope vocabulary anchor for `CAP-TENANCY`. `tenant_id` is the
sole canonical technical identifier; project is the only v1 subordinate scope and MUST NOT
exist without an associated tenant. Ownership composition reuses the existing
`ResourceOwnership` label set from `CAP-RESOURCE-OWNERSHIP` (never redefined here), and
`QuotaAuthority` declares — without enumerating dimensions — that this package is the sole
authority for tenant-level quota policy.
"""

from pydantic import BaseModel, ConfigDict, Field

from odoo_forge.resource_ownership.types import ResourceOwnership


class _TenancyValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class TenantId(_TenancyValue):
    """Canonical customer/client tenant identifier. The sole tenancy identity in v1."""

    value: str = Field(min_length=1)


class ProjectScope(_TenancyValue):
    """The only v1 subordinate scope; a project MUST NOT exist without its tenant."""

    tenant: TenantId
    project_id: str


class TenantScopedOwnership(_TenancyValue):
    """Composes tenant scope with the `CAP-RESOURCE-OWNERSHIP` label set.

    `ownership` reuses the imported `ResourceOwnership` enum rather than redefining
    `created`/`adopted`/`external` here.
    """

    tenant: TenantId
    project: ProjectScope | None = None
    ownership: ResourceOwnership


class QuotaAuthority(_TenancyValue):
    """Single tenant-level quota authority anchor. v1 declares the authority;
    concrete dimensions are deferred to a future revision, never to consumers."""

    tenant: TenantId


__all__ = [
    "ProjectScope",
    "QuotaAuthority",
    "TenantId",
    "TenantScopedOwnership",
]
