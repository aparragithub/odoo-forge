"""Workspace filesystem port — interface only, no adapter in this slice.

`odoo_forge` depends only on this structural interface. The concrete
adapter (git clone/fetch/worktree, filesystem scan) lives outside the core
package in a sibling package (`odoo_forge_workspace`, later slice) and MUST
NOT be imported here.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from odoo_forge.manifest.projection import ScannedRepo


@runtime_checkable
class WorkspaceProvider(Protocol):
    def checkout(self, url: str, commit: str, dest: Path) -> None:
        """Check out `url` at `commit` into `dest`."""
        ...

    def scan(self, roots: Sequence[Path]) -> list[ScannedRepo]:
        """Scan the given mount roots and return raw, un-attributed checkouts."""
        ...

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        """Promote a read-only checkout at `source` to a writable copy at `dest` on `branch`."""
        ...


__all__ = ["WorkspaceProvider"]
