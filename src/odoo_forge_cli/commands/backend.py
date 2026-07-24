"""Backend/instance-lifecycle commands: `run`, `status`, `stop`, `logs`, `exec`.

Helper modules (`_composition`, `_support`, `_presentation`) are imported and
called module-qualified so each moved symbol keeps exactly one canonical
patch target, per the design's module-qualified access decision. `plan_backend`
is imported with a bare `from ... import` (mirroring its pre-move shape in
`main.py`) — its call site resolves against THIS module's globals, so the
canonical patch target for `plan_backend` is
`odoo_forge_cli.commands.backend.plan_backend`. This module never imports
`odoo_forge_cli.main`.
"""

from pathlib import Path

import typer
from pydantic import ValidationError

from odoo_forge.backend.errors import BackendError
from odoo_forge.backend.plan import ContainerRole
from odoo_forge.backend.plan import plan_backend as plan_backend
from odoo_forge.backend.status import InstanceRef, derive_instance_ref
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.image_registry import RegistryError
from odoo_forge.image_registry.reference import normalize_image_reference
from odoo_forge.manifest.errors import ManifestError
from odoo_forge.manifest.projection import build_mount_planning_view, materialize_state
from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import _composition, _presentation, _support


def run(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    instance: str = typer.Option(
        "default", "--instance", help="Instance name, for running multiple copies side by side"
    ),
    odoo_image_ref: str | None = typer.Option(
        None,
        "--odoo-image-ref",
        help="Canonical digest-backed Odoo image reference for this run",
    ),
) -> None:
    """Provision the local Docker backend (Postgres + Odoo) for a manifest."""
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

    odoo_image: str | None = None
    if odoo_image_ref is not None:
        try:
            odoo_image = normalize_image_reference(odoo_image_ref, require_digest=True)
        except RegistryError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    # Resilient boundary, mirroring `project`/`unlock`: both a `ManifestError`
    # (e.g. `ScanError` from a corrupted checkout, raised by the SAME
    # `workspace_provider.scan`/`materialize_state` call `project`/`validate`
    # use), any `RegistryError` from a malformed runtime digest override, and
    # any `BackendError` (docker unavailable, image missing, registry
    # authorization denied, PG/Odoo readiness timeout, instance already
    # exists) surface as a single clean `error: ...` line, never a raw
    # traceback, and never a half-provisioned instance the caller doesn't know
    # about — `DockerBackendProvider.run` itself rolls back everything it
    # created before raising.
    try:
        host_roots = _support._host_roots(parsed)
        workspace_provider = _composition._make_manifest_workspace_provider(parsed)
        scanned = workspace_provider.scan(list(host_roots.values()))
        materialized = materialize_state(scanned, host_roots)
        mount_view = build_mount_planning_view(
            parsed,
            _support._load_lock(manifest.parent / "project.lock"),
            scanned,
            materialized,
            host_roots,
        )
        plan = plan_backend(
            parsed,
            mount_view,
            instance=instance,
            odoo_image=odoo_image,
            credentials=BackendCredentialBindings(
                odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
            ),
            postgres_credentials=CredentialHandle("local-backend/postgres-password"),
        )
        backend_provider = _composition._make_backend_provider(
            credentials_file=manifest.resolve().parent / "credentials.sops.yaml"
        )
        ref = backend_provider.run(plan)
    except (ManifestError, BackendError, RegistryError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"running: project '{ref.project}' instance '{ref.instance}' "
        f"(odoo '{ref.odoo_container}', postgres '{ref.postgres_container}')"
    )


def status(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    instance: str = typer.Option(
        "default", "--instance", help="Instance name, for running multiple copies side by side"
    ),
) -> None:
    """Report the local Docker backend's live state, never raising for an absent instance."""
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

    # No registry or workspace evidence is needed: identity is derived purely
    # from manifest/instance name, then handed to the provider's `status`.
    try:
        ref = derive_instance_ref(parsed, instance)
        backend_provider = _composition._make_backend_provider()
        report = backend_provider.status(ref)
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for role, role_status in (("postgres", report.postgres), ("odoo", report.odoo)):
        typer.echo(
            f"{role}: running={role_status.running} state={role_status.state} "
            f"ready={role_status.ready}"
        )


def _derive_ref(manifest: Path, instance: str) -> InstanceRef:
    """Derive an identity for state-independent instance commands."""
    parsed = Manifest.model_validate(_support._read_manifest_data(manifest))
    return derive_instance_ref(parsed, instance)


def stop(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    instance: str = typer.Option(
        "default", "--instance", help="Instance name, for running multiple copies side by side"
    ),
) -> None:
    """Stop and remove `ref`'s containers/network, preserving named volumes."""
    # Same boundary as `status`: malformed manifests, schema mismatches, and
    # backend errors surface as a single clean message, never a raw traceback.
    try:
        ref = _derive_ref(manifest, instance)
        backend_provider = _composition._make_backend_provider()
        backend_provider.stop(ref)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"stopped: project '{ref.project}' instance '{ref.instance}'")


def logs(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    instance: str = typer.Option(
        "default", "--instance", help="Instance name, for running multiple copies side by side"
    ),
    role: ContainerRole = typer.Option(
        "odoo", "--role", help="Which container's logs to fetch (odoo or postgres)"
    ),
) -> None:
    """Print `role`'s container log text for the derived instance."""
    try:
        ref = _derive_ref(manifest, instance)
        backend_provider = _composition._make_backend_provider()
        text = backend_provider.logs(ref, role)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(text)


def exec_(
    ctx: typer.Context,
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
    instance: str = typer.Option(
        "default", "--instance", help="Instance name, for running multiple copies side by side"
    ),
) -> None:
    """Run the trailing ARGV inside the Odoo container, propagating its exit code."""
    argv = list(ctx.args)

    # Resilient boundary identical to `stop`/`logs`: a `ManifestError`/
    # `ValidationError`/`BackendError` (including an absent instance) exits
    # clean with a single-line message and code 1 — that is a DIFFERENT,
    # error-boundary exit distinct from a successful `exec` whose command
    # itself returned a non-zero code, which propagates `ExecResult.exit_code`
    # verbatim below.
    try:
        ref = _derive_ref(manifest, instance)
        backend_provider = _composition._make_backend_provider()
        result = backend_provider.exec(ref, argv)
    except ValidationError as exc:
        _presentation._render_validation_errors(exc)
        raise typer.Exit(code=1) from exc
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr, err=True)
    raise typer.Exit(code=result.exit_code)


def register(app: typer.Typer) -> None:
    """Bind the five backend/instance-lifecycle commands onto `app`, byte-identical names."""
    app.command(name="run")(run)
    app.command(name="status")(status)
    app.command(name="stop")(stop)
    app.command(name="logs")(logs)
    app.command(
        name="exec",
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )(exec_)
