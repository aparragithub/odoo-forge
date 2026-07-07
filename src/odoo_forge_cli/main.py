"""Thin Typer presentation layer for `forge`.

No domain logic lives here: parsing, composition, and drift detection are
delegated entirely to `odoo_forge`. This module only reads files, translates
I/O and decode failures into typed domain errors, calls the core, and renders
results — including turning structured `DriftEntry` values into human text.
"""

import json
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.drift import DriftEntry, detect_drift
from odoo_forge.manifest.errors import LockfileError, ManifestError, ManifestInputError
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.schema import Manifest

app = typer.Typer()


@app.callback()
def _forge_callback() -> None:
    """Odoo Forge — decentralized project manifest tooling."""


def _read_manifest_data(path: Path) -> object:
    """Read + YAML-parse the manifest, raising a typed error on any failure."""
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError) as exc:
        raise ManifestInputError(f"cannot read manifest '{path}': {exc}") from exc

    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestInputError(f"malformed YAML in manifest '{path}': {exc}") from exc


def _load_lock(path: Path) -> Lockfile | None:
    """Load and validate the lockfile, or return None if it does not exist."""
    if not path.exists():
        return None

    try:
        raw = path.read_text()
    except (PermissionError, UnicodeDecodeError, OSError) as exc:
        raise LockfileError(f"cannot read lockfile '{path}': {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LockfileError(f"invalid JSON in lockfile '{path}': {exc}") from exc

    try:
        return Lockfile.model_validate(data)
    except ValidationError as exc:
        raise LockfileError(f"invalid lockfile '{path}': {exc}") from exc


def _format_drift(entry: DriftEntry) -> str:
    """Render a structured drift entry as a single human-readable line."""
    if entry.kind == "missing_lock":
        return "no lockfile present — manifest has never been locked"
    if entry.kind == "manifest_lock_hash":
        return f"manifest hash '{entry.expected}' does not match lock's '{entry.actual}'"
    if entry.kind == "not_materialized":
        target = f"layer '{entry.layer}'"
        if entry.repo:
            target += f" repo '{entry.repo}'"
        return f"{target} is not materialized"
    if entry.kind == "commit_mismatch":
        return (
            f"layer '{entry.layer}' repo '{entry.repo}' lock declares "
            f"'{entry.expected}' but materialized at '{entry.actual}'"
        )
    return f"unrecognized drift entry: {entry.kind}"


@app.command()
def validate(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Parse, compose, and report lock drift for a manifest."""
    try:
        data = _read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            typer.echo(f"error: {location}: {error['msg']}", err=True)
        raise typer.Exit(code=1)

    # Compose and load/validate the lock BEFORE announcing success, so a corrupt
    # lock is reported as a clear error rather than after a misleading "is valid".
    try:
        compose(parsed)
        lock = _load_lock(manifest.parent / "project.lock")
        report = detect_drift(parsed, lock, materialized=None)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"{manifest} is valid")

    if lock is None:
        return

    # Only manifest<->lock drift is checked here; materialized (on-disk) state
    # is deferred to a later slice, so the message stays scoped to what ran.
    if report.is_clean:
        typer.echo("no manifest/lock drift detected")
    else:
        for entry in report.manifest_lock_drift + report.lock_state_drift:
            typer.echo(f"drift: {_format_drift(entry)}")


__all__ = ["app"]
