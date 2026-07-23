"""Composition roots: the ONE place each concrete adapter is constructed.

No domain logic lives here — these factories exist so `odoo_forge_cli`'s
Typer commands can obtain a concrete `SourceProvider`/`WorkspaceProvider`/
`BackendProvider`/image-registry adapter without importing adapter packages
directly into command bodies.
"""

import os
from pathlib import Path

from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.backend_provider import BackendProvider
from odoo_forge.ports.published_artifact_resolver import PublishedArtifactResolver
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge.project_catalog.interfaces import CatalogIndex
from odoo_forge_catalog import YamlCatalogIndex
from odoo_forge_docker.credential_injection import SopsCommandResolver, SopsEnvFileInjector
from odoo_forge_docker.provider import DockerBackendProvider
from odoo_forge_git.git_provider import GitSourceProvider
from odoo_forge_registry import GhcrImageRegistryProvider, PublishedArtifactRegistryResolver
from odoo_forge_workspace.provider import GitWorkspaceProvider

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


def _make_catalog_index(*, catalog_path: Path = Path("catalog.yaml")) -> CatalogIndex:
    """Composition root: the ONE place the concrete catalog adapter is built."""
    return YamlCatalogIndex(catalog_path)


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
