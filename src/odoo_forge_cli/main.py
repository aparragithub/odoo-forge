"""Thin Typer presentation layer for `forge`.

No domain logic lives here: parsing, composition, and drift detection are
delegated entirely to `odoo_forge`. This module only reads files, translates
I/O and decode failures into typed domain errors, calls the core, and renders
results — including turning structured `DriftEntry` values into human text.
"""

import json
import os
import tempfile
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.drift import DriftEntry, detect_drift
from odoo_forge.manifest.errors import (
    LockfileError,
    ManifestError,
    ManifestInputError,
    ResolutionError,
)
from odoo_forge.manifest.locking import build_lock
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.projection import (
    MOUNT_ROOTS,
    materialize_state,
    plan_projection,
    project_workspace,
)
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge_git.git_provider import GitSourceProvider
from odoo_forge_workspace.provider import GitWorkspaceProvider

app = typer.Typer()


def _make_provider() -> SourceProvider:
    """Composition root: the ONE place the concrete git adapter is built."""
    return GitSourceProvider()


def _make_workspace_provider() -> WorkspaceProvider:
    """Composition root: the ONE place the concrete workspace adapter is built."""
    return GitWorkspaceProvider()


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
        return Lockfile.from_json(raw)
    except json.JSONDecodeError as exc:
        raise LockfileError(f"invalid JSON in lockfile '{path}': {exc}") from exc
    except ValidationError as exc:
        raise LockfileError(f"invalid lockfile '{path}': {exc}") from exc


def _write_lock_atomic(lock_path: Path, content: str) -> None:
    """Write `content` to `lock_path` atomically.

    Writes to a temp file in the SAME directory, then renames it into place
    with `os.replace` — an atomic operation on POSIX and Windows. This
    guarantees a pre-existing `project.lock` is never truncated/corrupted by
    a partial write, and stays intact until the new content is fully on
    disk. On failure the temp file is removed and the original (if any) is
    left untouched; the raised `OSError` propagates to the caller.
    """
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=lock_path.parent, prefix=f".{lock_path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w") as tmp_file:
            tmp_file.write(content)
        os.replace(tmp_path, lock_path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


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
        provider = _make_workspace_provider()
        scanned = provider.scan(list(MOUNT_ROOTS.values()))
        materialized = materialize_state(scanned, MOUNT_ROOTS)
        report = detect_drift(parsed, lock, materialized)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"{manifest} is valid")

    if lock is None:
        return

    # Both manifest<->lock and lock<->on-disk-state drift are checked here:
    # `materialized` is a real `MaterializedState` scanned from the fixed
    # mount roots, so `not_materialized`/`commit_mismatch` entries reflect
    # the actual workspace, not a hardcoded `None`.
    if report.is_clean:
        typer.echo("no manifest/lock drift detected")
    else:
        for entry in report.manifest_lock_drift + report.lock_state_drift:
            typer.echo(f"drift: {_format_drift(entry)}")


@app.command()
def lock(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Resolve every declared ref to a commit SHA and write `project.lock`."""
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

    # Resilient boundary, mirroring `validate`: a `CompositionError`, any
    # `ResolutionError` (ref-not-found/auth/network), or an `OSError` while
    # writing surfaces as a single clean message, never a raw traceback, and
    # never leaves a partial/corrupt `project.lock` on disk — the write
    # itself is atomic (temp file + `os.replace`), so a failure here also
    # leaves a pre-existing lock byte-identical.
    lock_path = manifest.parent / "project.lock"
    try:
        provider = _make_provider()
        lockfile = build_lock(parsed, provider)
        _write_lock_atomic(lock_path, lockfile.to_canonical_json())
    except (ManifestError, ResolutionError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"wrote {lock_path}")


@app.command(name="project")
def project(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    lock: Path = typer.Option(
        None,
        "--lock",
        help="Path to the project.lock file (default: alongside the manifest)",
    ),
) -> None:
    """Project a locked manifest onto the filesystem under fixed mount roots."""
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

    lock_path = lock if lock is not None else manifest.parent / "project.lock"

    # Resilient boundary, mirroring `lock`: `ProjectionError` (orphaned locked
    # layer) and any `WorkspaceError` from the adapter (e.g. `CheckoutError`)
    # surface as a single clean message naming the failing repo, never a raw
    # traceback. `project_workspace` stops at the first failing step and
    # never touches already-completed steps.
    try:
        loaded_lock = _load_lock(lock_path)
        if loaded_lock is None:
            raise LockfileError(f"no lockfile found at '{lock_path}' — run `forge lock` first")

        plan = plan_projection(parsed, loaded_lock)
        provider = _make_workspace_provider()
        project_workspace(plan, provider)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"projected {len(plan.steps)} repo(s) from {lock_path}")


__all__ = ["app"]
