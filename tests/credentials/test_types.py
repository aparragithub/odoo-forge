import pytest
from pydantic import ValidationError

from odoo_forge.credentials import TargetContext
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle


def test_target_context_accepts_source_kind_for_enterprise_git_fetch() -> None:
    target = TargetContext(kind="source", target_id="enterprise")

    assert target.model_dump() == {"kind": "source", "target_id": "enterprise"}


# -- Phase 4: credential convergence (design "Credential convergence") --
#
# `postgres_password` is retired from `BackendCredentialBindings`: Postgres
# credential injection is now owned exclusively by the adapter's
# `PostgreSQLSecretInjection`, and the handle travels via
# `BackendPlan.postgres_credentials` instead. This REPLACES the prior
# characterization test that pinned `postgres_password`'s presence
# (`test_current_backend_credential_bindings_still_carries_postgres_password`),
# which is retired here now that the removal has landed.


def test_backend_credential_bindings_no_longer_carries_postgres_password() -> None:
    bindings = BackendCredentialBindings(
        odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
    )

    assert bindings.model_dump() == {"odoo_db_password": "local-backend/odoo-db-password"}


def test_backend_credential_bindings_rejects_postgres_password_kwarg() -> None:
    with pytest.raises(ValidationError):
        BackendCredentialBindings(
            postgres_password=CredentialHandle("local-backend/postgres-password"),  # type: ignore[call-arg]
            odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
        )
