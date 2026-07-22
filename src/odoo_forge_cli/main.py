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

from odoo_forge.backend.errors import BackendError
from odoo_forge.backend.plan import ContainerRole, plan_backend
from odoo_forge.backend.status import InstanceRef, derive_instance_ref
from odoo_forge.credentials.doctor import run_doctor
from odoo_forge.credentials.errors import CredentialError
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.image_registry import RegistryError
from odoo_forge.image_registry.reference import (
    normalize_digest_image_reference,
    normalize_image_reference,
    normalize_publishable_image_reference,
)
from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.drift import DriftEntry, detect_drift
from odoo_forge.manifest.errors import (
    LockfileError,
    ManifestError,
    ManifestInputError,
    ModuleDependencyError,
    ResolutionError,
)
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.locking import build_lock
from odoo_forge.manifest.module_deps import build_module_index, find_missing_dependencies
from odoo_forge.manifest.projection import (
    build_mount_planning_view,
    build_mount_roots,
    materialize_state,
    ordered_addons_roots,
    plan_projection,
    plan_unlock,
    project_workspace,
)
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.backend_provider import BackendProvider
from odoo_forge.ports.published_artifact_resolver import PublishedArtifactResolver
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge_cli.enterprise_credential import (
    _bind_enterprise_source_provider,
    _bind_enterprise_workspace_provider,
    _make_enterprise_credential_resolver,
    _preflight_enterprise_source_credential,
)
from odoo_forge_docker.credential_injection import (
    SopsCommandResolver,
    SopsEnvFileInjector,
)
from odoo_forge_docker.credential_injection import (
    rotate_enterprise_credential as _rotate_enterprise_credential,
)
from odoo_forge_docker.provider import DockerBackendProvider
from odoo_forge_git.git_provider import GitSourceProvider
from odoo_forge_registry import GhcrImageRegistryProvider, PublishedArtifactRegistryResolver
from odoo_forge_workspace.provider import GitWorkspaceProvider

app = typer.Typer()

_WORKSPACE_PROVIDER_TIMEOUT_SECONDS: float | None = None


def _make_provider() -> SourceProvider:
    """Composition root: the ONE place the concrete git adapter is built."""
    return GitSourceProvider()


def _make_published_artifact_resolver() -> PublishedArtifactResolver:
    """Composition root: the registry adapter stays outside the pure core."""
    return PublishedArtifactRegistryResolver(GhcrImageRegistryProvider())


def _make_workspace_provider() -> WorkspaceProvider:
    """Composition root: the ONE place the concrete workspace adapter is built."""
    timeout = _WORKSPACE_PROVIDER_TIMEOUT_SECONDS
    if timeout is None:
        return GitWorkspaceProvider()
    return GitWorkspaceProvider(timeout=timeout)


def _make_manifest_workspace_provider(manifest: Manifest) -> WorkspaceProvider:
    timeout = None
    if manifest.workspace is not None:
        timeout = manifest.workspace.checkout_timeout_seconds

    global _WORKSPACE_PROVIDER_TIMEOUT_SECONDS
    previous_timeout = _WORKSPACE_PROVIDER_TIMEOUT_SECONDS
    _WORKSPACE_PROVIDER_TIMEOUT_SECONDS = float(timeout) if timeout is not None else None
    try:
        return _make_workspace_provider()
    finally:
        _WORKSPACE_PROVIDER_TIMEOUT_SECONDS = previous_timeout


def _make_backend_provider(
    *, credentials_file: Path = Path("credentials.sops.yaml")
) -> BackendProvider:
    """Composition root: the ONE place the concrete docker adapter is built."""
    return DockerBackendProvider(
        credential_injector=SopsEnvFileInjector(SopsCommandResolver(credentials_file))
    )


def _make_image_registry_provider() -> GhcrImageRegistryProvider:
    """Composition root: the ONE place the concrete registry adapter is built."""
    return GhcrImageRegistryProvider()


def _doctor_age_key_file() -> Path | None:
    """Composition root: the age keyfile path `forge doctor` checks.

    Honors `SOPS_AGE_KEY_FILE` when set (mirrors `sops`'s own env var);
    returns `None` otherwise so `check_age_key_present` falls back to its
    own default (`~/.config/sops/age/keys.txt`).
    """
    override = os.environ.get("SOPS_AGE_KEY_FILE")
    return Path(override) if override else None


def _resolve_mount_base() -> Path:
    """Composition root: resolve the HOST mount base from the environment.

    `odoo_forge` core never reads environment variables — this is the ONE
    place `FORGE_MOUNT_BASE`/`XDG_STATE_HOME` are consulted. Mirrors
    `DockerBackendProvider._default_authority`
    (`odoo_forge_postgres_docker/provider.py:481-489`). Precedence:
    `FORGE_MOUNT_BASE` (if truthy) wins; else
    `${XDG_STATE_HOME:-~/.local/state} / "odoo-forge"`. An empty-string
    `FORGE_MOUNT_BASE` is treated as unset.

    The resolved base must be absolute: it becomes the source token of the
    Docker `-v <source>:<target>` bind mount, and Docker silently reinterprets
    a non-absolute source as a *named volume* rather than a host bind mount.
    A relative `FORGE_MOUNT_BASE` therefore fails fast with a clear error; a
    non-absolute `XDG_STATE_HOME` is ignored per the XDG Base Directory spec.
    """
    base = os.environ.get("FORGE_MOUNT_BASE")
    if base:
        resolved = Path(base).expanduser()
        if not resolved.is_absolute():
            raise ManifestInputError(f"FORGE_MOUNT_BASE must be an absolute path, got {base!r}")
        return resolved
    state = os.environ.get("XDG_STATE_HOME")
    state_home = (
        Path(state) if state and Path(state).is_absolute() else Path.home() / ".local" / "state"
    )
    return state_home.expanduser() / "odoo-forge"


def _host_roots(manifest: Manifest) -> dict[str, Path]:
    """Build the HOST mount-root table for `manifest`.

    Slice 2 (pure mount model): `build_mount_roots` is manifest-derived, so
    the HOST table can no longer be computed once at import time — every
    manifest may declare a different set of custom categories. Resolution
    still happens through the one composition-root function,
    `_resolve_mount_base`; only its result is now threaded per-manifest
    instead of cached in a module-level global.
    """
    return build_mount_roots(_resolve_mount_base(), manifest)


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
    except (ValidationError, ValueError) as exc:
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


def _format_missing_dependencies(missing: dict[str, frozenset[str]]) -> str:
    """Render every module's missing dependencies as one sorted, multi-line message."""
    lines = [f"  {name} -> {', '.join(sorted(deps))}" for name, deps in sorted(missing.items())]
    return "missing module dependencies:\n" + "\n".join(lines)


def _check_module_dependencies(parsed: Manifest, base: Path) -> None:
    """Run module-dependency validation against the materialized addons_path.

    Shared by `validate` (after drift detection confirms the workspace is
    materialized) and `onboard` (right after `project_workspace` completes
    and the post-projection drift check confirms a clean, fully materialized
    tree) — both are commands whose flow ends with a real addons_path on
    disk. `forge lock` deliberately does NOT call this: it only resolves refs
    and writes `project.lock`, it never checks out a workspace itself, so
    there is no addons_path to inspect at that point (running this check
    there would only see stale evidence from a previous `onboard`, if any).

    Raises `ModuleDependencyError` (caught by the existing
    `except ManifestError` handler) for both a malformed `__manifest__.py`
    and any missing dependency.
    """
    addons_roots = ordered_addons_roots(parsed, base=base)
    try:
        index = build_module_index(addons_roots)
    except ValueError as exc:
        raise ModuleDependencyError(str(exc)) from exc
    missing = find_missing_dependencies(index)
    if missing:
        raise ModuleDependencyError(_format_missing_dependencies(missing))


def _render_validation_errors(exc: ValidationError) -> None:
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        typer.echo(f"error: {location}: {error['msg']}", err=True)


@app.command(name="image-resolve")
def image_resolve(ref: str = typer.Option(..., "--ref", help="Image reference to resolve")) -> None:
    """Resolve a supported GHCR image reference to a canonical digest ref."""
    try:
        normalized_ref = normalize_publishable_image_reference(ref)
        provider = _make_image_registry_provider()
        typer.echo(provider.resolve_digest(normalized_ref))
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="image-publish")
def image_publish(
    ref: str = typer.Option(..., "--ref", help="Image reference to publish"),
) -> None:
    """Publish a built GHCR image and print its immutable digest ref."""
    try:
        normalized_ref = normalize_publishable_image_reference(ref)
        provider = _make_image_registry_provider()
        typer.echo(provider.publish(normalized_ref))
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="image-pull")
def image_pull(
    ref: str = typer.Option(..., "--ref", help="Digest image reference to prefetch"),
) -> None:
    """Prefetch a digest image into the local Docker daemon."""
    try:
        normalized_ref = normalize_digest_image_reference(ref)
        provider = _make_image_registry_provider()
        typer.echo(provider.pull(normalized_ref))
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="image-exists")
def image_exists(
    ref: str = typer.Option(..., "--ref", help="Digest image reference to check"),
) -> None:
    """Check whether a digest image exists in the registry."""
    try:
        normalized_ref = normalize_digest_image_reference(ref)
        provider = _make_image_registry_provider()
        typer.echo(str(provider.exists(normalized_ref)).lower())
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    # Compose and load/validate the lock BEFORE announcing success, so a corrupt
    # lock is reported as a clear error rather than after a misleading "is valid".
    try:
        compose(parsed)
        lock = _load_lock(manifest.parent / "project.lock")
        host_roots = _host_roots(parsed)
        provider = _make_manifest_workspace_provider(parsed)
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
            _check_module_dependencies(parsed, _resolve_mount_base())
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
            typer.echo(f"drift: {_format_drift(entry)}")


@app.command()
def onboard(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Validate local inputs, materialize the workspace, and print the next step."""
    try:
        data = _read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
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
        loaded_lock = _load_lock(lock_path)
        if loaded_lock is None:
            raise LockfileError(f"no lockfile found at '{lock_path}' — run `forge lock` first")

        host_roots = _host_roots(parsed)
        plan = plan_projection(parsed, loaded_lock, host_roots)
        provider: WorkspaceProvider = _make_manifest_workspace_provider(parsed)
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
            raise ManifestError(f"drift: {_format_drift(blocking_drift[0])}")

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
            raise ManifestError(f"drift: {_format_drift(drift_entry)}")

        # The workspace is now confirmed materialized and drift-free — the
        # same real module-dependency check `forge validate` runs, so a user
        # who never calls `forge validate` still gets it here. `forge lock`
        # does NOT get this check (see `_check_module_dependencies`'s
        # docstring): it never materializes a workspace itself.
        _check_module_dependencies(parsed, _resolve_mount_base())
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except CredentialError as exc:
        typer.echo(f"error: Enterprise credential required but unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"onboarded workspace with {len(plan.steps)} repo(s) from {lock_path}")
    typer.echo(f"next: run `forge validate --manifest {manifest}`")


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
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    # Resilient boundary, mirroring `validate`: a `CompositionError`, any
    # `ResolutionError` (ref-not-found/auth/network), or an `OSError` while
    # writing surfaces as a single clean message, never a raw traceback, and
    # never leaves a partial/corrupt `project.lock` on disk — the write
    # itself is atomic (temp file + `os.replace`), so a failure here also
    # leaves a pre-existing lock byte-identical.
    lock_path = manifest.parent / "project.lock"
    try:
        provider: SourceProvider = _make_provider()
        resolver = _make_enterprise_credential_resolver(
            credentials_file=manifest.resolve().parent / "credentials.sops.yaml"
        )
        # Fail fast BEFORE any fetch (community or Enterprise): a missing
        # SOPS entry or an unusable age key must abort `lock` immediately,
        # never fall through to an unauthenticated fetch attempt. No-op for
        # non-enterprise editions.
        _preflight_enterprise_source_credential(parsed, resolver)
        provider = _bind_enterprise_source_provider(parsed, provider, resolver)
        artifact_resolver = _make_published_artifact_resolver()
        lockfile = build_lock(parsed, provider, artifact_resolver)
        _write_lock_atomic(lock_path, lockfile.to_canonical_json())
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
        data = _read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

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

        plan = plan_projection(parsed, loaded_lock, _host_roots(parsed))
        provider = _make_manifest_workspace_provider(parsed)
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
        data = _read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    # Resilient boundary, mirroring `project`: `ProjectionError` (unknown
    # layer) and any `WorkspaceError` from the adapter (`AlreadyUnlockedError`,
    # `PromotionError`) surface as a single clean message, never a raw
    # traceback. `source`/`dest`/`branch` are computed here in the pure core
    # (`plan_unlock`) — the adapter only executes the worktree move.
    try:
        unlock_plan = plan_unlock(parsed, layer, repo, _host_roots(parsed))
        provider = _make_manifest_workspace_provider(parsed)
        provider.promote(unlock_plan.source, unlock_plan.dest, unlock_plan.branch)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"unlocked '{layer}' at '{unlock_plan.dest}' on branch '{unlock_plan.branch}'")


@app.command(name="run")
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
        data = _read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
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
        host_roots = _host_roots(parsed)
        workspace_provider = _make_manifest_workspace_provider(parsed)
        scanned = workspace_provider.scan(list(host_roots.values()))
        materialized = materialize_state(scanned, host_roots)
        mount_view = build_mount_planning_view(
            parsed,
            _load_lock(manifest.parent / "project.lock"),
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
                postgres_password=CredentialHandle("local-backend/postgres-password"),
                odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
            ),
        )
        backend_provider = _make_backend_provider(
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


@app.command(name="status")
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
        data = _read_manifest_data(manifest)
    except ManifestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        parsed = Manifest.model_validate(data)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc

    # No registry or workspace evidence is needed: identity is derived purely
    # from manifest/instance name, then handed to the provider's `status`.
    try:
        ref = derive_instance_ref(parsed, instance)
        backend_provider = _make_backend_provider()
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
    parsed = Manifest.model_validate(_read_manifest_data(manifest))
    return derive_instance_ref(parsed, instance)


@app.command(name="stop")
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
        backend_provider = _make_backend_provider()
        backend_provider.stop(ref)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"stopped: project '{ref.project}' instance '{ref.instance}'")


@app.command(name="logs")
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
        backend_provider = _make_backend_provider()
        text = backend_provider.logs(ref, role)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(text)


@app.command(
    name="exec",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
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
        backend_provider = _make_backend_provider()
        result = backend_provider.exec(ref, argv)
    except ValidationError as exc:
        _render_validation_errors(exc)
        raise typer.Exit(code=1) from exc
    except (ManifestError, BackendError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr, err=True)
    raise typer.Exit(code=result.exit_code)


@app.command(name="doctor")
def doctor(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Check local Enterprise credential prerequisites: age key + conventional SOPS entry.

    Thin CLI wiring only — both checks' logic lives in
    `odoo_forge.credentials.doctor.run_doctor`. Reports both checks
    independently and never prints secret material.
    """
    resolver = _make_enterprise_credential_resolver(
        credentials_file=manifest.resolve().parent / "credentials.sops.yaml"
    )
    report = run_doctor(resolver=resolver, age_key_file=_doctor_age_key_file())
    for check in (report.age_key, report.enterprise_credential):
        status = "ok" if check.ok else "FAIL"
        typer.echo(f"{status}: {check.name}: {check.message}")
    if not report.ok:
        raise typer.Exit(code=1)


@app.command(name="rotate-enterprise-credential")
def rotate_enterprise_credential(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Rotate the conventional Enterprise source credential's SOPS keys.

    Thin CLI wiring only — the `sops updatekeys` wrapper itself lives in
    `odoo_forge_docker.credential_injection.rotate_enterprise_credential`
    (the docker adapter, since core is forbidden from importing
    `subprocess`). Touches no schema/state file; only
    `credentials.sops.yaml` is rewritten by `sops`.
    """
    credentials_file = manifest.resolve().parent / "credentials.sops.yaml"
    result = _rotate_enterprise_credential(credentials_file=credentials_file)
    if not result.ok:
        typer.echo(f"error: {result.message}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.message)


__all__ = [
    "app",
    "_bind_enterprise_source_provider",
    "_bind_enterprise_workspace_provider",
    "_make_enterprise_credential_resolver",
    "_preflight_enterprise_source_credential",
]
