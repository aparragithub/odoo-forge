"""Pure default-ref substitution, zero I/O.

`resolve_default_ref` is a standalone, opt-in helper — never wired into
`compose()`. It exists so the future git adapter (Phase 2 Slice 2b) can
resolve an unset `core.ref` to a branch name before doing a SHA lookup,
without changing the pure composition contract.
"""

from odoo_forge.manifest.schema import CoreLayer, EnterpriseLayer


def resolve_default_ref(core: CoreLayer | EnterpriseLayer, odoo_version: str) -> str:
    """Return `core.ref` unchanged when set, else `odoo_version`.

    Pure: never mutates `core`, performs zero I/O.
    """
    return core.ref if core.ref is not None else odoo_version


__all__ = ["resolve_default_ref"]
