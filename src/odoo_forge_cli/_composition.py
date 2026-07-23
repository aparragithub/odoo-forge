"""Composition roots: the ONE place each concrete adapter is constructed.

No domain logic lives here — these factories exist so `odoo_forge_cli`'s
Typer commands can obtain a concrete `SourceProvider`/`WorkspaceProvider`/
`BackendProvider`/image-registry adapter without importing adapter packages
directly into command bodies.
"""

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from odoo_forge.anonymization.apply import MaskTransform
from odoo_forge.credentials.errors import CredentialUnavailableError
from odoo_forge.credentials.types import CredentialHandle, CredentialInjectionDescriptor
from odoo_forge.data_artifacts.coordinator import DataArtifactCopyCoordinator
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.backend_provider import BackendProvider
from odoo_forge.ports.database_provider import DatabaseProvider
from odoo_forge.ports.pipeline_provider import PipelineProvider
from odoo_forge.ports.published_artifact_resolver import PublishedArtifactResolver
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge.project_catalog.interfaces import CatalogIndex
from odoo_forge_catalog import YamlCatalogIndex
from odoo_forge_docker.credential_injection import SopsCommandResolver, SopsEnvFileInjector
from odoo_forge_docker.provider import DockerBackendProvider
from odoo_forge_git.git_provider import GitSourceProvider
from odoo_forge_postgres_docker.capture import DockerPostgresqlCaptureAdapter
from odoo_forge_postgres_docker.mask_transform import make_docker_mask_transform
from odoo_forge_postgres_docker.provider import DockerPostgresqlDatabaseProvider
from odoo_forge_postgres_docker.restore_target import make_docker_restore_target
from odoo_forge_postgres_docker.staged_capability import (
    StagedArtifactCapability,
    make_staged_byte_source,
)
from odoo_forge_postgres_docker.staged_store import (
    FilesystemStagedArtifactStore,
    default_staged_artifact_store_root,
)
from odoo_forge_pipeline_github.provider import GitHubActionsPipelineProvider
from odoo_forge_pipeline_github.transport import GitHubActionsRestTransport
from odoo_forge_registry import GhcrImageRegistryProvider, PublishedArtifactRegistryResolver
from odoo_forge_workspace.provider import GitWorkspaceProvider

_WORKSPACE_PROVIDER_TIMEOUT_SECONDS: float | None = None


class PipelineConfigurationError(RuntimeError):
    """Raised when a required pipeline env var is unset."""


def _require_pipeline_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise PipelineConfigurationError(f"missing required environment variable: {name}")
    return value


def _make_pipeline_provider() -> PipelineProvider:
    """Composition root: the ONE place the concrete pipeline adapter is built."""
    token = _require_pipeline_env("FORGE_PIPELINE_GITHUB_TOKEN")
    owner = _require_pipeline_env("FORGE_PIPELINE_GITHUB_OWNER")
    repo = _require_pipeline_env("FORGE_PIPELINE_GITHUB_REPO")
    ref = _require_pipeline_env("FORGE_PIPELINE_GITHUB_REF")
    transport = GitHubActionsRestTransport(token=token, owner=owner, repo=repo)
    return GitHubActionsPipelineProvider(transport=transport, owner=owner, repo=repo, ref=ref)


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


def _sops_credential_target(
    credentials_file: Path,
) -> Callable[[CredentialInjectionDescriptor], AbstractContextManager[str]]:
    """Bridge the postgres adapter's opaque `sops://<handle>` descriptor to
    the SAME `SopsCommandResolver` the Odoo credential leg already uses."""
    resolver = SopsCommandResolver(credentials_file)

    @contextmanager
    def _target(descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        if descriptor.target_kind != "database" or not descriptor.store_ref.startswith("sops://"):
            raise CredentialUnavailableError()
        handle = descriptor.store_ref.removeprefix("sops://")
        yield resolver(CredentialHandle(handle))

    return _target


def _make_database_provider(
    *, credentials_file: Path = Path("credentials.sops.yaml")
) -> DatabaseProvider:
    """Composition root: the ONE place the concrete postgres adapter is built."""
    return DockerPostgresqlDatabaseProvider(
        credential_target=_sops_credential_target(credentials_file)
    )


def _make_backend_provider(
    *, credentials_file: Path = Path("credentials.sops.yaml")
) -> BackendProvider:
    """Composition root: the ONE place the concrete docker adapter is built."""
    return DockerBackendProvider(
        credential_injector=SopsEnvFileInjector(SopsCommandResolver(credentials_file)),
        database_provider=_make_database_provider(credentials_file=credentials_file),
    )


def _make_mask_transform(store: StagedArtifactStore) -> MaskTransform:
    """Composition root: the ONE place the concrete `MaskTransform` is built.

    Replaces the previous pass-through, which returned every component untouched
    while the coordinator recorded `event="anonymization_applied"` — audit
    evidence claiming a masking step that never ran. Real per-rule byte masking
    now happens via a scratch-database round trip
    (`odoo_forge_postgres_docker.mask_transform`), staging the masked bytes into
    the SAME store so the re-persisted manifest's digest matches real bytes
    (design D11).

    An empty policy is still a genuine no-op: the transform returns the
    component unchanged rather than round-tripping a dump for no reason.
    """
    return make_docker_mask_transform(store=store)


def _make_staged_artifact_store(*, root: Path | None = None) -> FilesystemStagedArtifactStore:
    """Composition root: the ONE place the concrete staged artifact store is built."""
    return FilesystemStagedArtifactStore(root or default_staged_artifact_store_root())


def _make_data_artifact_copy_coordinator(
    *, credentials_file: Path = Path("credentials.sops.yaml")
) -> DataArtifactCopyCoordinator:
    """Composition root: the ONE place the `copy` command's durable capture ->
    anonymize -> deliver coordinator is built (bridge slice B5).

    Wires the store-backed `StagedArtifactCapability` and byte source
    (bridge slice B2) into BOTH the capture adapter (bridge slice B3) and the
    real `RestoreTarget` (bridge slice B4/D1), and passes `store.put` as
    `manifest_persistence` (design D11) so the coordinator's re-persisted
    masked manifest is byte-consistent with the store by construction.
    """
    store = _make_staged_artifact_store()
    artifact_capability = StagedArtifactCapability(store)
    capture_capability = DockerPostgresqlCaptureAdapter(store=store)
    database_provider = DockerPostgresqlDatabaseProvider(
        credential_target=_sops_credential_target(credentials_file),
        artifact_capability=artifact_capability,
        restore_injector=make_docker_restore_target(byte_source=make_staged_byte_source(store)),
    )
    return DataArtifactCopyCoordinator(
        capture_capability=capture_capability,
        artifact_capability=artifact_capability,
        database_provider=database_provider,
        mask_transform=_make_mask_transform(store),
        manifest_persistence=store.put,
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
