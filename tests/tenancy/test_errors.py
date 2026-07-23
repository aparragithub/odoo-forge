import pytest

from odoo_forge.tenancy import (
    CrossTenantAccessError,
    ProjectWithoutTenantError,
    QuotaExceededError,
    TenancyError,
    UnknownTenantError,
)


@pytest.mark.parametrize(
    "error_type",
    [UnknownTenantError, ProjectWithoutTenantError, CrossTenantAccessError, QuotaExceededError],
)
def test_error_subclasses_tenancy_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, TenancyError)


def test_unknown_tenant_error_preserves_tenant_id() -> None:
    error = UnknownTenantError(tenant_id="t1")

    assert error.tenant_id == "t1"


def test_project_without_tenant_error_preserves_project_id() -> None:
    error = ProjectWithoutTenantError(project_id="p1")

    assert error.project_id == "p1"


def test_cross_tenant_access_error_preserves_tenant_ids() -> None:
    error = CrossTenantAccessError(requested_tenant_id="t1", resource_tenant_id="t2")

    assert error.requested_tenant_id == "t1"
    assert error.resource_tenant_id == "t2"


def test_quota_exceeded_error_preserves_tenant_id() -> None:
    error = QuotaExceededError(tenant_id="t1")

    assert error.tenant_id == "t1"
