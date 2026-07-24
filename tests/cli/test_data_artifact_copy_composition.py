"""Unit tests for the `copy` command's composition root (bridge slice B5).

Exercises the REAL wiring (`FilesystemStagedArtifactStore` +
`StagedArtifactCapability` + store-backed byte source + real `RestoreTarget` +
`DockerPostgresqlDatabaseProvider`) that
`_composition._make_data_artifact_copy_coordinator` assembles, without ever
invoking `docker` (this module never calls `.run()` on the coordinator).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_forge.anonymization.policy import AnonymizationRule, MaskStrategy
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
)
from odoo_forge.data_artifacts.coordinator import DataArtifactCopyCoordinator
from odoo_forge_cli import _composition
from odoo_forge_postgres_docker.provider import DockerPostgresqlDatabaseProvider
from odoo_forge_postgres_docker.staged_capability import StagedArtifactCapability
from odoo_forge_postgres_docker.staged_store import FilesystemStagedArtifactStore

_DIGEST = ArtifactDigest(algorithm="sha256", value="0" * 64)


def _component(kind: ArtifactComponentKind) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=kind, opaque_component_ref="component-1", format_version="v1", digest=_DIGEST
    )


def test_make_staged_artifact_store_defaults_under_xdg_state_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    store = _composition._make_staged_artifact_store()

    assert isinstance(store, FilesystemStagedArtifactStore)
    assert store.root == tmp_path / "odoo-forge" / "artifact-store"


def test_make_staged_artifact_store_honors_an_explicit_root(tmp_path: Path) -> None:
    root = tmp_path / "custom-store-root"

    store = _composition._make_staged_artifact_store(root=root)

    assert store.root == root


def test_make_data_artifact_copy_coordinator_wires_the_staged_store_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    coordinator = _composition._make_data_artifact_copy_coordinator()

    assert isinstance(coordinator, DataArtifactCopyCoordinator)
    artifact_capability = coordinator._artifact_capability
    assert isinstance(artifact_capability, StagedArtifactCapability)
    store = artifact_capability._store
    assert isinstance(store, FilesystemStagedArtifactStore)
    assert store.root == tmp_path / "odoo-forge" / "artifact-store"
    database_provider = coordinator._database_provider
    assert isinstance(database_provider, DockerPostgresqlDatabaseProvider)
    # The provider's artifact capability and the coordinator's must be the SAME
    # instance so `validate_for_restore`/`discard` and `restore()`'s internal
    # `validated_database_restore` agree on the same staged store.
    assert database_provider._artifact_capability is artifact_capability
    # `manifest_persistence` is wired to the REAL store's `put`, not the
    # coordinator's optional no-op default (design D11).
    assert coordinator._manifest_persistence == store.put


def test_pass_through_mask_transform_is_identity_for_an_empty_policy() -> None:
    component = _component(ArtifactComponentKind.DATABASE)

    result = _composition._pass_through_mask_transform(component, ())

    assert result is component


def test_pass_through_mask_transform_fails_closed_for_a_non_empty_policy() -> None:
    component = _component(ArtifactComponentKind.DATABASE)
    rule = AnonymizationRule(table="res_partner", column="email", mask_strategy=MaskStrategy.REDACT)

    with pytest.raises(NotImplementedError):
        _composition._pass_through_mask_transform(component, (rule,))
