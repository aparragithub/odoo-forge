"""Concrete git `SourceProvider` adapter — the only I/O boundary that shells
out to `git`. Kept as a sibling package to `odoo_forge` so core stays free of
`subprocess`/`git` imports (enforced by the 3rd import-linter contract).
"""

from odoo_forge_git.git_provider import GitSourceProvider

__all__ = ["GitSourceProvider"]
