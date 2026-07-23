"""Thin Typer presentation layer for `forge`.

No domain logic lives here: parsing, composition, and drift detection are
delegated entirely to `odoo_forge`. This module only reads files, translates
I/O and decode failures into typed domain errors, calls the core, and renders
results — including turning structured `DriftEntry` values into human text.
"""

from pathlib import Path

import typer
from pydantic import ValidationError

from odoo_forge.credentials.errors import CredentialError
from odoo_forge.manifest.errors import (
    LockfileError,
    ManifestError,
    ResolutionError,
)
from odoo_forge.manifest.locking import build_lock
from odoo_forge.manifest.projection import (
    plan_projection,
    plan_unlock,
    project_workspace,
)
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge_cli import _composition, _presentation, _support
from odoo_forge_cli.commands import backend, image, maintenance, manifest
from odoo_forge_cli.enterprise_credential import (
    _bind_enterprise_source_provider,
    _bind_enterprise_workspace_provider,  # noqa: F401 -- kept for main._bind_enterprise_workspace_provider (test_enterprise_credential.py, repointed in PR5b per design's out-of-scope split)
    _make_enterprise_credential_resolver,
    _preflight_enterprise_source_credential,
)

app = typer.Typer()


@app.callback()
def _forge_callback() -> None:
    """Odoo Forge — decentralized project manifest tooling."""


backend.register(app)
image.register(app)
maintenance.register(app)
manifest.register(app)


@app.command()
def lock(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Resolve every declared ref to a commit SHA and write `project.lock`."""
    try:
        data = _support._read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    # Resilient boundary, mirroring `validate`: a `CompositionError`, any
    # `ResolutionError` (ref-not-found/auth/network), or an `OSError` while
    # writing surfaces as a single clean message, never a raw traceback, and
    # never leaves a partial/corrupt `project.lock` on disk — the write
    # itself is atomic (temp file + `os.replace`), so a failure here also
    # leaves a pre-existing lock byte-identical.
    lock_path = manifest.parent / "project.lock"
    try:
        provider: SourceProvider = _composition._make_provider()
        resolver = _make_enterprise_credential_resolver(
            credentials_file=manifest.resolve().parent / "credentials.sops.yaml"
        )
        # Fail fast BEFORE any fetch (community or Enterprise): a missing
        # SOPS entry or an unusable age key must abort `lock` immediately,
        # never fall through to an unauthenticated fetch attempt. No-op for
        # non-enterprise editions.
        _preflight_enterprise_source_credential(parsed, resolver)
        provider = _bind_enterprise_source_provider(parsed, provider, resolver)
        artifact_resolver = _composition._make_published_artifact_resolver()
        lockfile = build_lock(parsed, provider, artifact_resolver)
        _support._write_lock_atomic(lock_path, lockfile.to_canonical_json())
    except (ManifestError, ResolutionError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except CredentialError as exc:
        typer.echo(f"error: Enterprise credential required but unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc

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
        data = _support._read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    lock_path = lock if lock is not None else manifest.parent / "project.lock"

    # Resilient boundary, mirroring `lock`: `ProjectionError` (orphaned locked
    # layer) and any `WorkspaceError` from the adapter (e.g. `CheckoutError`)
    # surface as a single clean message naming the failing repo, never a raw
    # traceback. `project_workspace` stops at the first failing step and
    # never touches already-completed steps.
    try:
        loaded_lock = _support._load_lock(lock_path)
        if loaded_lock is None:
            raise LockfileError(f"no lockfile found at '{lock_path}' — run `forge lock` first")

        plan = plan_projection(parsed, loaded_lock, _support._host_roots(parsed))
        provider = _composition._make_manifest_workspace_provider(parsed)
        project_workspace(plan, provider)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"projected {len(plan.steps)} repo(s) from {lock_path}")


@app.command(name="unlock")
def unlock(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    layer: str = typer.Option(..., "--layer", help="Name of the layer to promote"),
    repo: str = typer.Option(..., "--repo", help="URL of the repo within the layer to promote"),
) -> None:
    """Promote a repo's read-only projected checkout to a writable worktree."""
    try:
        data = _support._read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    # Resilient boundary, mirroring `project`: `ProjectionError` (unknown
    # layer) and any `WorkspaceError` from the adapter (`AlreadyUnlockedError`,
    # `PromotionError`) surface as a single clean message, never a raw
    # traceback. `source`/`dest`/`branch` are computed here in the pure core
    # (`plan_unlock`) — the adapter only executes the worktree move.
    try:
        unlock_plan = plan_unlock(parsed, layer, repo, _support._host_roots(parsed))
        provider = _composition._make_manifest_workspace_provider(parsed)
        provider.promote(unlock_plan.source, unlock_plan.dest, unlock_plan.branch)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"unlocked '{layer}' at '{unlock_plan.dest}' on branch '{unlock_plan.branch}'")


__all__ = [
    "app",
    "_bind_enterprise_source_provider",
    "_bind_enterprise_workspace_provider",
    "_make_enterprise_credential_resolver",
    "_preflight_enterprise_source_credential",
]
