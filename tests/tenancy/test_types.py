from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.resource_ownership.types import ResourceOwnership
from odoo_forge.tenancy import ProjectScope, QuotaAuthority, TenantId, TenantScopedOwnership


def _tenant(value: str = "t1") -> TenantId:
    return TenantId(value=value)


def test_tenant_id_is_frozen_and_forbids_unknown_fields() -> None:
    tenant = _tenant()

    assert tenant.value == "t1"
    with pytest.raises(ValidationError):
        cast(Any, tenant).value = "t2"
    with pytest.raises(ValidationError):
        TenantId(value="t1", extra_field="nope")  # type: ignore[call-arg]


def test_tenant_id_rejects_empty_value() -> None:
    with pytest.raises(ValidationError):
        TenantId(value="")


def test_project_scope_requires_tenant() -> None:
    with pytest.raises(ValidationError):
        ProjectScope(project_id="p1")  # type: ignore[call-arg]


def test_project_scope_constructs_with_tenant() -> None:
    scope = ProjectScope(tenant=_tenant(), project_id="p1")

    assert scope.tenant == _tenant()
    assert scope.project_id == "p1"


def test_tenant_scoped_ownership_reuses_imported_resource_ownership_enum() -> None:
    ownership_field = TenantScopedOwnership.model_fields["ownership"]

    assert ownership_field.annotation is ResourceOwnership


def test_tenant_scoped_ownership_accepts_none_or_project_scope() -> None:
    unattributed = TenantScopedOwnership(
        tenant=_tenant(), project=None, ownership=ResourceOwnership.EXTERNAL
    )
    attributed = TenantScopedOwnership(
        tenant=_tenant(),
        project=ProjectScope(tenant=_tenant(), project_id="p1"),
        ownership=ResourceOwnership.CREATED,
    )

    assert unattributed.project is None
    assert attributed.project is not None
    assert attributed.project.project_id == "p1"


def test_quota_authority_exposes_only_tenant_field() -> None:
    authority = QuotaAuthority(tenant=_tenant())

    assert set(authority.model_fields) == {"tenant"}
