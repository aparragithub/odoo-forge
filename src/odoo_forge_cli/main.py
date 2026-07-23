"""Thin Typer presentation layer for `forge`.

No domain logic lives here: parsing, composition, and drift detection are
delegated entirely to `odoo_forge`. `main.py` only builds the `app`, defines
the top-level callback, and registers each command family's commands via
`register(app)`.
"""

import typer

from odoo_forge_cli.commands import backend, image, maintenance, manifest

app = typer.Typer()


@app.callback()
def _forge_callback() -> None:
    """Odoo Forge — decentralized project manifest tooling."""


backend.register(app)
image.register(app)
maintenance.register(app)
manifest.register(app)
