"""Immutable image-registry resolution/validation port.

`odoo_forge` depends only on this structural interface. Concrete registry
adapters live outside the core package and MUST NOT be imported here.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ImageRegistryProvider(Protocol):
    def resolve(self, ref: str) -> str:
        """Resolve `ref` to a canonical digest reference."""
        ...

    def validate(self, ref: str) -> str:
        """Validate a digest-backed `ref` and return its canonical form."""
        ...


__all__ = ["ImageRegistryProvider"]
