"""Source resolution port — interface only, no adapter in this slice.

`odoo_forge` depends only on this structural interface. Concrete adapters
(git clone/fetch, registry lookups, etc.) live outside the core package in
a later slice and MUST NOT be imported here.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SourceProvider(Protocol):
    def resolve_ref(self, url: str, ref: str) -> str:
        """Resolve a `url`/`ref` pair to a concrete commit SHA."""
        ...


__all__ = ["SourceProvider"]
