"""Typed, redacted tenancy contract failures.

Enforcement is deferred to future consumers; these types declare the normative failure
surface for `CAP-TENANCY` exactly once (unknown tenant, project without tenant association,
cross-tenant access, and quota exceeded).
"""


class TenancyError(Exception):
    """Base class for tenancy contract failures."""


class UnknownTenantError(TenancyError):
    """Raised when an operation references a `tenant_id` with no corresponding tenant."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"unknown tenant '{tenant_id}'")


class ProjectWithoutTenantError(TenancyError):
    """Raised when a project is referenced without an associated tenant."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"project '{project_id}' has no associated tenant")


class CrossTenantAccessError(TenancyError):
    """Raised when a consumer attempts to access a resource scoped to a different tenant."""

    def __init__(self, requested_tenant_id: str, resource_tenant_id: str) -> None:
        self.requested_tenant_id = requested_tenant_id
        self.resource_tenant_id = resource_tenant_id
        super().__init__(
            f"tenant '{requested_tenant_id}' may not access a resource scoped to "
            f"tenant '{resource_tenant_id}'"
        )


class QuotaExceededError(TenancyError):
    """Raised when a tenant exceeds its quota. Reserves the surface; enforcement deferred."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"tenant '{tenant_id}' exceeded its quota")


__all__ = [
    "CrossTenantAccessError",
    "ProjectWithoutTenantError",
    "QuotaExceededError",
    "TenancyError",
    "UnknownTenantError",
]
