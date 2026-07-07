from odoo_forge.manifest.resolution import resolve_default_ref
from odoo_forge.manifest.schema import CoreLayer


def test_none_ref_resolves_to_odoo_version() -> None:
    core = CoreLayer()

    resolved = resolve_default_ref(core, "19.0")

    assert resolved == "19.0"


def test_explicit_ref_preserved_unchanged() -> None:
    core = CoreLayer(ref="17.0-custom")

    resolved = resolve_default_ref(core, "19.0")

    assert resolved == "17.0-custom"


def test_helper_does_not_mutate_core() -> None:
    core = CoreLayer()

    resolve_default_ref(core, "19.0")

    assert core.ref is None
