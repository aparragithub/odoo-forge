from odoo_forge.manifest.lockfile import compute_manifest_hash
from odoo_forge.manifest.schema import Manifest


def _manifest_a() -> Manifest:
    return Manifest.model_validate(
        {
            "name": "odoo-idp",
            "odoo_version": "19.0",
            "edition": "community",
            "client": {"addons_path": "client/addons"},
        }
    )


def _manifest_b() -> Manifest:
    # Same semantic content, built via a dict with different key order.
    return Manifest.model_validate(
        {
            "client": {"addons_path": "client/addons"},
            "edition": "community",
            "odoo_version": "19.0",
            "name": "odoo-idp",
        }
    )


def test_hash_stable_across_key_order() -> None:
    # Guards INPUT-side stability: two dicts with different key order parse to an
    # equal Manifest and therefore hash identically (Pydantic normalizes order).
    # This does not exercise json.dumps(sort_keys=True); see the comment in
    # compute_manifest_hash for why sort_keys guards future dict-typed fields.
    hash_a = compute_manifest_hash(_manifest_a())
    hash_b = compute_manifest_hash(_manifest_b())

    assert hash_a == hash_b


def test_hash_differs_when_content_differs() -> None:
    hash_a = compute_manifest_hash(_manifest_a())

    changed = _manifest_a()
    changed.name = "different-name"
    hash_changed = compute_manifest_hash(changed)

    assert hash_a != hash_changed
