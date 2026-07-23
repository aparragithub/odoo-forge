"""Manifest-lifecycle commands: `validate`, `onboard` (PR5a); `lock`,
`project`, `unlock` join in PR5b.

Helper modules (`_composition`, `_support`, `_presentation`) are imported and
called module-qualified so each moved symbol keeps exactly one canonical
patch target, per the design's module-qualified access decision. This module
never imports `odoo_forge_cli.main`.
"""

from pathlib import Path

import typer
from pydantic import ValidationError

from odoo_forge.credentials.errors import CredentialError
from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.drift import detect_drift
from odoo_forge.manifest.errors import LockfileError, ManifestError
from odoo_forge.manifest.projection import materialize_state, plan_projection, project_workspace
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge_cli import _composition, _presentation, _support
from odoo_forge_cli.enterprise_credential import (
    _bind_enterprise_workspace_provider,
    _make_enterprise_credential_resolver,
    _preflight_enterprise_source_credential,
)


def validate(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Parse, compose, and report lock drift for a manifest."""
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

    # Compose and load/validate the lock BEFORE announcing success, so a corrupt
    # lock is reported as a clear error rather than after a misleading "is valid".
    try:
        compose(parsed)
        lock = _support._load_lock(manifest.parent / "project.lock")
        host_roots = _support._host_roots(parsed)
        provider = _composition._make_manifest_workspace_provider(parsed)
        scanned = provider.scan(list(host_roots.values()))
        materialized = materialize_state(scanned, host_roots)
        report = detect_drift(parsed, lock, materialized)
        if lock is not None:
            # A mount root that is not yet materialized (partial
            # `forge onboard`/`forge project`) must never silently read as
            # "module missing" — build_module_index would just see an empty
            # or partial addons_path and misreport it. Fail loud and
            # distinctly instead of running the dependency check at all.
            not_materialized = [
                entry
                for entry in report.manifest_lock_drift + report.lock_state_drift
                if entry.kind == "not_materialized"
            ]
            if not_materialized:
                raise ManifestError(
                    "workspace not fully materialized — run `forge onboard` "
                    "(or `forge project`) before module-dependency validation can run"
                )
            _support._check_module_dependencies(parsed, _support._resolve_mount_base())
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

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
            typer.echo(f"drift: {_presentation._format_drift(entry)}")


def onboard(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Validate local inputs, materialize the workspace, and print the next step."""
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

    lock_path = manifest.parent / "project.lock"
    try:
        resolver = _make_enterprise_credential_resolver(
            credentials_file=manifest.resolve().parent / "credentials.sops.yaml"
        )
        # Fail fast BEFORE any fetch (community or Enterprise): identical
        # contract to `lock`'s preflight check — see that comment.
        _preflight_enterprise_source_credential(parsed, resolver)

        compose(parsed)
        loaded_lock = _support._load_lock(lock_path)
        if loaded_lock is None:
            raise LockfileError(f"no lockfile found at '{lock_path}' — run `forge lock` first")

        host_roots = _support._host_roots(parsed)
        plan = plan_projection(parsed, loaded_lock, host_roots)
        provider: WorkspaceProvider = _composition._make_manifest_workspace_provider(parsed)
        provider = _bind_enterprise_workspace_provider(parsed, provider, resolver)
        scanned = provider.scan(list(host_roots.values()))
        materialized = materialize_state(scanned, host_roots)
        preflight = detect_drift(parsed, loaded_lock, materialized)
        blocking_drift = [
            entry
            for entry in preflight.manifest_lock_drift + preflight.lock_state_drift
            if entry.kind != "not_materialized"
        ]
        if blocking_drift:
            raise ManifestError(f"drift: {_presentation._format_drift(blocking_drift[0])}")

        project_workspace(plan, provider)

        scanned = provider.scan(list(host_roots.values()))
        materialized = materialize_state(scanned, host_roots)
        final_report = detect_drift(parsed, loaded_lock, materialized)
        if not final_report.is_clean:
            drift_entry = (
                final_report.manifest_lock_drift[0]
                if final_report.manifest_lock_drift
                else final_report.lock_state_drift[0]
            )
            raise ManifestError(f"drift: {_presentation._format_drift(drift_entry)}")

        # The workspace is now confirmed materialized and drift-free — the
        # same real module-dependency check `forge validate` runs, so a user
        # who never calls `forge validate` still gets it here. `forge lock`
        # does NOT get this check (see `_check_module_dependencies`'s
        # docstring): it never materializes a workspace itself.
        _support._check_module_dependencies(parsed, _support._resolve_mount_base())
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except CredentialError as exc:
        typer.echo(f"error: Enterprise credential required but unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"onboarded workspace with {len(plan.steps)} repo(s) from {lock_path}")
    typer.echo(f"next: run `forge validate --manifest {manifest}`")


def register(app: typer.Typer) -> None:
    """Bind manifest commands onto `app`, byte-identical names.

    Extended in PR5b to also bind `lock`, `project`, `unlock`.
    """
    app.command(name="validate")(validate)
    app.command(name="onboard")(onboard)
