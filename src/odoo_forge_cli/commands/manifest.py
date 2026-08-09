"""Manifest-lifecycle commands: `configure`, `validate`, `onboard`, `lock`, `project`,
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
from odoo_forge.manifest.authoring import validate_draft
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


def _prompt_text(message: str, default: str | None = None) -> str:
    if default is None:
        return str(typer.prompt(message))
    return str(typer.prompt(message, default=default, show_default=bool(default)))


def _optional_number(value: str) -> object:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _collect_git_layer() -> dict[str, object]:
    name = _prompt_text("Layer name")
    category = _prompt_text("Layer category", "custom")
    repos: list[dict[str, str]] = []
    while True:
        repos.append(
            {
                "url": _prompt_text("Repository URL"),
                "ref": _prompt_text("Repository ref"),
            }
        )
        if not typer.confirm("Add another repository?", default=False):
            break
    return {
        "type": "git",
        "name": name,
        "repos": repos,
        "category": category,
    }


def _collect_published_layer() -> dict[str, object]:
    return {
        "type": "published",
        "name": _prompt_text("Published layer name"),
        "source": _prompt_text("Published layer source"),
        "version": _prompt_text("Published layer version"),
        "category": _prompt_text("Published layer category", "custom"),
        "requires_enterprise": typer.confirm("Published layer requires enterprise", default=False),
    }


def _collect_layers() -> list[dict[str, object]]:
    layers: list[dict[str, object]] = []
    while typer.confirm("Add a layer?" if not layers else "Add another layer?", default=False):
        layers.append(_collect_git_layer())
    return layers


def _collect_overrides() -> list[dict[str, str]]:
    overrides: list[dict[str, str]] = []
    while typer.confirm(
        "Add an override?" if not overrides else "Add another override?", default=False
    ):
        overrides.append(
            {
                "layer": _prompt_text("Override layer"),
                "repo": _prompt_text("Override repository"),
                "fork": _prompt_text("Override fork"),
                "ref": _prompt_text("Override ref"),
            }
        )
    return overrides


def _collect_mount_priority(layers: list[dict[str, object]]) -> list[str]:
    categories = {str(layer["category"]) for layer in layers if layer.get("category")}
    roots = ["worktrees", "community", "enterprise"] + [
        f"custom/{'default' if category == 'custom' else category}"
        for category in sorted(categories)
    ]
    priority: list[str] = []
    while typer.confirm(
        "Add mount priority?" if not priority else "Add another mount priority?", default=False
    ):
        priority.append(_prompt_text(f"Mount priority root (choose from {', '.join(roots)})"))
    return priority


def _collect_draft() -> dict[str, object]:
    name = _prompt_text("Project name")
    odoo_version = _prompt_text("Odoo version")
    edition = _prompt_text("Edition (community or enterprise)").lower()
    draft: dict[str, object] = {
        "name": name,
        "odoo_version": odoo_version,
        "edition": edition,
    }
    core_url = _prompt_text("Core URL override", "")
    core_ref = _prompt_text("Core ref override", "")
    if core_url or core_ref:
        draft["core"] = {
            "type": "core",
            **({"url": core_url} if core_url else {}),
            **({"ref": core_ref} if core_ref else {}),
        }
    if edition == "enterprise":
        enterprise_url = _prompt_text("Enterprise URL override", "")
        enterprise_ref = _prompt_text("Enterprise ref override", "")
        if enterprise_url or enterprise_ref:
            draft["enterprise"] = {
                "type": "enterprise",
                **({"url": enterprise_url} if enterprise_url else {}),
                **({"ref": enterprise_ref} if enterprise_ref else {}),
            }

    layers = _collect_layers()
    draft["layers"] = layers
    addons_path = _prompt_text("Client addons path")
    draft["client"] = {"addons_path": addons_path}
    draft["overrides"] = _collect_overrides()

    if typer.confirm("Configure workspace", default=False):
        draft["workspace"] = {
            "checkout_timeout_seconds": _optional_number(_prompt_text("Workspace checkout timeout"))
        }
    if typer.confirm("Configure backend", default=False):
        odoo: dict[str, object] = {}
        port = _optional_number(_prompt_text("Odoo HTTP port", ""))
        bind_host = _prompt_text("Odoo bind host", "127.0.0.1")
        if port is not None:
            odoo["http_port"] = port
        if bind_host != "127.0.0.1":
            odoo["bind_host"] = bind_host
        draft["backend"] = {"odoo": odoo}
    draft["mount_priority"] = _collect_mount_priority(layers)
    return draft


def configure(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the new project.yaml manifest"
    ),
) -> None:
    """Guide creation of a new project.yaml without entering execution scope."""
    if manifest.exists():
        typer.echo(f"error: target already exists: {manifest}", err=True)
        raise typer.Exit(code=1)

    result = validate_draft(_collect_draft())
    if result.manifest is None:
        for issue in result.issues:
            typer.echo(f"error: {issue.path}: {issue.message}", err=True)
        raise typer.Exit(code=1)

    content = _support.serialize_manifest(result.manifest)
    typer.echo("YAML preview:")
    typer.echo(content, nl=False)
    if not typer.confirm("Create this project.yaml?", default=False):
        typer.echo("cancelled; no file was created")
        raise typer.Exit(code=0)
    try:
        _support._write_manifest_create_only(manifest, content)
    except FileExistsError:
        typer.echo(f"error: target already exists: {manifest}", err=True)
        raise typer.Exit(code=1) from None
    except OSError as exc:
        typer.echo(f"error: cannot create '{manifest}': {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"created {manifest}")


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
                odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
            ),
            postgres_credentials=CredentialHandle("local-backend/postgres-password"),
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
    app.command(name="configure")(configure)
    app.command(name="validate")(validate)
    app.command(name="onboard")(onboard)
    app.command(name="lock")(lock)
    app.command(name="project")(project)
    app.command(name="unlock")(unlock)
