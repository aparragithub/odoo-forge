from odoo_forge.credentials import TargetContext


def test_target_context_accepts_source_kind_for_enterprise_git_fetch() -> None:
    target = TargetContext(kind="source", target_id="enterprise")

    assert target.model_dump() == {"kind": "source", "target_id": "enterprise"}
