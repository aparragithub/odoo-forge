"""Thin Typer presentation layer for `forge`.

No domain logic lives here: parsing, composition, and drift detection are
delegated entirely to `odoo_forge`. This module only reads files, calls the
core, and prints results.
"""

import json
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.errors import CompositionError
from odoo_forge.manifest.drift import detect_drift
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.schema import Manifest

app = typer.Typer()


@app.callback()
def _forge_callback() -> None:
    """Odoo Forge — decentralized project manifest tooling."""


@app.command()
def validate(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Parse, compose, and report lock drift for a manifest."""
    try:
        parsed = Manifest.model_validate(yaml.safe_load(manifest.read_text()))
    except ValidationError as exc:
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            typer.echo(f"error: {location}: {error['msg']}")
        raise typer.Exit(code=1)

    try:
        compose(parsed)
    except CompositionError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"{manifest} is valid")

    lock_path = manifest.parent / "project.lock"
    if lock_path.exists():
        lock = Lockfile.model_validate(json.loads(lock_path.read_text()))
        report = detect_drift(parsed, lock, materialized=None)
        if report.is_clean:
            typer.echo("no drift detected")
        else:
            for entry in report.manifest_lock_drift + report.lock_state_drift:
                typer.echo(f"drift: {entry}")


__all__ = ["app"]
