"""Filesystem, environment, and manifest-I/O helpers shared by `forge` commands.

No domain logic lives here: parsing, composition, and drift detection are
delegated entirely to `odoo_forge`. This module only reads files, translates
I/O and decode failures into typed domain errors, and resolves the ONE
composition-root path (the HOST mount base) that depends on the environment.
"""

import json
import os
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from odoo_forge.manifest.errors import LockfileError, ManifestInputError, ModuleDependencyError
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.module_deps import build_module_index, find_missing_dependencies
from odoo_forge.manifest.projection import build_mount_roots, ordered_addons_roots
from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import _presentation


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
        raise ModuleDependencyError(_presentation._format_missing_dependencies(missing))
