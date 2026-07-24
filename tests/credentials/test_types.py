from odoo_forge.credentials import TargetContext
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle


def test_target_context_accepts_source_kind_for_enterprise_git_fetch() -> None:
    target = TargetContext(kind="source", target_id="enterprise")

    assert target.model_dump() == {"kind": "source", "target_id": "enterprise"}


# -- characterization: baseline `BackendCredentialBindings` shape --
#
# Pins the pre-cutover shape (`postgres_password` still present) before
# Phase 4 removes it in favor of `BackendPlan.postgres_credentials` (design
# "Credential convergence").


def test_current_backend_credential_bindings_still_carries_postgres_password() -> None:
    bindings = BackendCredentialBindings(
        postgres_password=CredentialHandle("local-backend/postgres-password"),
        odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
    )

    assert bindings.model_dump() == {
        "postgres_password": "local-backend/postgres-password",
        "odoo_db_password": "local-backend/odoo-db-password",
    }
