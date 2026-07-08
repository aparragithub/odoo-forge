"""Concrete git `WorkspaceProvider` adapter — the only I/O boundary that shells
out to `git` for workspace projection. Kept as a sibling package to
`odoo_forge` so core stays free of `subprocess`/`git` imports (enforced by
the 4th import-linter contract).
"""

from odoo_forge_workspace.provider import GitWorkspaceProvider

__all__ = ["GitWorkspaceProvider"]
