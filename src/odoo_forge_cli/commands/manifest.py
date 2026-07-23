"""Manifest-lifecycle commands: `validate`, `onboard`, `lock`, `project`,
`unlock`.

Helper modules (`_composition`, `_support`, `_presentation`) are imported and
called module-qualified so each moved symbol keeps exactly one canonical
patch target, per the design's module-qualified access decision. This module
never imports `odoo_forge_cli.main`.
"""

from pathlib import Path

import typer
from pydantic import ValidationError

from odoo_forge.backend.errors import BackendError
from odoo_forge.backend.plan import plan_backend
from odoo_forge.credentials.errors import CredentialError
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.image_registry import RegistryError
from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.drift import detect_drift
from odoo_forge.manifest.errors import LockfileError, ManifestError, ResolutionError
from odoo_forge.manifest.locking import build_lock
from odoo_forge.manifest.projection import (
    build_mount_planning_view,
    materialize_state,
    plan_projection,
    plan_unlock,
    project_workspace,
)
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge.project_catalog.models import ProjectCatalogRequest, ProjectCatalogResolutionFailure
from odoo_forge.project_catalog.resolver import ProjectCatalogResolver
from odoo_forge_catalog.errors import CatalogSourceError
from odoo_forge_cli import _composition, _presentation, _support
from odoo_forge_cli.enterprise_credential import (
    _bind_enterprise_source_provider,
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
    client: str | None = typer.Argument(
        None, help="Client identifier to resolve via the project catalog"
    ),
    manifest: Path | None = typer.Option(
        None, "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Validate/materialize local inputs (`--manifest`), or resolve, materialize, and
    start an instance for a catalog-known client (positional `<cliente>`)."""
    try:
        if client is not None and manifest is not None:
            raise ManifestError("onboard accepts either a client name or --manifest, not both")
        if client is None and manifest is None:
            raise ManifestError("onboard requires either a client name or --manifest <path>")
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if manifest is not None:
        _onboard_manifest_mode(manifest)
        return
    assert client is not None
    _onboard_catalog_mode(client)


def _onboard_manifest_mode(manifest: Path) -> None:
    """Legacy local-input path: validate, materialize, print the next step.

    Byte-identical to `onboard`'s pre-dual-mode behavior — no catalog lookup,
    no backend/instance creation.
    """
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


def _onboard_catalog_mode(client: str) -> None:
    """Catalog-driven path: resolve `client`, materialize repos, start an instance.

    Reuses the existing manifest/lock/projection pipeline
    (`plan_projection`/`project_workspace`) and the existing backend pipeline
    (`plan_backend`/`DockerBackendProvider.run`) verbatim — only the manifest
    path's source (a resolved catalog record instead of `--manifest`)
    differs. `data_policy_default`/`target_default` are transported on the
    resolved result but deliberately never read here (ADR-0001: no seeding,
    no remote-target actioning this slice).
    """
    catalog_index = _composition._make_catalog_index()
    resolver = ProjectCatalogResolver(catalog_index)
    request = ProjectCatalogRequest(client_key=client)
    try:
        resolution = resolver.resolve(request)
    except CatalogSourceError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if isinstance(resolution, ProjectCatalogResolutionFailure):
        typer.echo(f"error: {resolution.type}: {resolution.details}", err=True)
        raise typer.Exit(code=1)

    manifest_path = Path(resolution.manifest_ref.manifest_path)

    try:
        data = _support._read_manifest_data(manifest_path)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    lock_path = manifest_path.parent / "project.lock"
    try:
        enterprise_resolver = _make_enterprise_credential_resolver(
            credentials_file=manifest_path.resolve().parent / "credentials.sops.yaml"
        )
        # Fail fast BEFORE any fetch (community or Enterprise): identical
        # contract to `lock`'s preflight check and `_onboard_manifest_mode` —
        # see that comment.
        _preflight_enterprise_source_credential(parsed, enterprise_resolver)

        compose(parsed)
        loaded_lock = _support._load_lock(lock_path)
        if loaded_lock is None:
            raise LockfileError(f"no lockfile found at '{lock_path}' — run `forge lock` first")

        host_roots = _support._host_roots(parsed)
        plan = plan_projection(parsed, loaded_lock, host_roots)
        provider: WorkspaceProvider = _composition._make_manifest_workspace_provider(parsed)
        provider = _bind_enterprise_workspace_provider(parsed, provider, enterprise_resolver)
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

        # Same module-dependency safety net `_onboard_manifest_mode` runs
        # once the workspace is confirmed materialized and drift-free.
        _support._check_module_dependencies(parsed, _support._resolve_mount_base())

        mount_view = build_mount_planning_view(
            parsed, loaded_lock, scanned, materialized, host_roots
        )
        backend_plan = plan_backend(
            parsed,
            mount_view,
            instance="default",
            odoo_image=None,
            credentials=BackendCredentialBindings(
                postgres_password=CredentialHandle("local-backend/postgres-password"),
                odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
            ),
        )
        backend_provider = _composition._make_backend_provider(
            credentials_file=manifest_path.resolve().parent / "credentials.sops.yaml"
        )
        ref = backend_provider.run(backend_plan)
    except (ManifestError, BackendError, RegistryError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except CredentialError as exc:
        typer.echo(f"error: Enterprise credential required but unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"running: project '{ref.project}' instance '{ref.instance}' "
        f"(odoo '{ref.odoo_container}', postgres '{ref.postgres_container}')"
    )


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


def register(app: typer.Typer) -> None:
    """Bind manifest commands onto `app`, byte-identical names."""
    app.command(name="validate")(validate)
    app.command(name="onboard")(onboard)
    app.command(name="lock")(lock)
    app.command(name="project")(project)
    app.command(name="unlock")(unlock)
