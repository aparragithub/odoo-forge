import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import ScannedRepo, build_mount_roots
from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import main
from odoo_forge_cli.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

runner = CliRunner()


class _FakeScanningWorkspaceProvider:
    """A `WorkspaceProvider` double whose `scan` returns caller-supplied
    `ScannedRepo` facts — no real filesystem/git I/O."""

    def __init__(self, scanned: list[ScannedRepo]) -> None:
        self._scanned = scanned

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        raise NotImplementedError

    def scan(self, roots: object) -> list[ScannedRepo]:
        return self._scanned

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def test_valid_manifest_exits_zero() -> None:
    result = runner.invoke(
        app, ["validate", "--manifest", str(FIXTURES_DIR / "valid.project.yaml")]
    )

    assert result.exit_code == 0


def test_malformed_manifest_single_cause_error_nonzero_exit() -> None:
    result = runner.invoke(
        app, ["validate", "--manifest", str(FIXTURES_DIR / "malformed.project.yaml")]
    )

    assert result.exit_code != 0
    assert result.output.count("error:") == 1


def test_missing_manifest_file_clear_error_exit_one(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"

    result = runner.invoke(app, ["validate", "--manifest", str(missing)])

    assert result.exit_code == 1
    assert result.output.startswith("error:") or "\nerror:" in result.output
    assert "Traceback" not in result.output


def test_malformed_yaml_syntax_clear_error_exit_one(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "project.yaml"
    # Unbalanced bracket — a YAML *syntax* error, distinct from a schema error.
    bad_yaml.write_text("name: [unclosed\n")

    result = runner.invoke(app, ["validate", "--manifest", str(bad_yaml)])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "YAML" in result.output
    assert "Traceback" not in result.output


def test_composition_error_clear_error_exit_one(tmp_path: Path) -> None:
    # Parses fine, but community edition + enterprise-requiring layer fails compose().
    manifest = tmp_path / "project.yaml"
    manifest.write_text(
        "name: odoo-idp\n"
        "odoo_version: '19.0'\n"
        "edition: community\n"
        "layers:\n"
        "  - type: published\n"
        "    name: enterprise\n"
        "    source: registry://example/odoo-ee\n"
        "    version: '19.0.1'\n"
        "    requires_enterprise: true\n"
        "client:\n"
        "  addons_path: client/addons\n"
    )

    result = runner.invoke(app, ["validate", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "enterprise" in result.output
    assert "is valid" not in result.output
    assert "Traceback" not in result.output


def test_corrupt_lock_json_clear_error_no_false_success(tmp_path: Path) -> None:
    manifest_path = FIXTURES_DIR / "valid.project.yaml"
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(manifest_path.read_text())
    (tmp_path / "project.lock").write_text("{ this is not valid json")

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert "error:" in result.output
    # No misleading success line before the lock error.
    assert "is valid" not in result.output
    assert "Traceback" not in result.output


def test_structurally_invalid_lock_clear_error_exit_one(tmp_path: Path) -> None:
    manifest_path = FIXTURES_DIR / "valid.project.yaml"
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(manifest_path.read_text())
    # Valid JSON, but missing the required `generated_from` field.
    (tmp_path / "project.lock").write_text(json.dumps({"layers": []}))

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "is valid" not in result.output
    assert "Traceback" not in result.output


def test_no_drift_when_lock_matches_manifest_hash_exit_zero(tmp_path: Path) -> None:
    manifest_path = FIXTURES_DIR / "valid.project.yaml"
    manifest = Manifest.model_validate(yaml.safe_load(manifest_path.read_text()))

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(manifest_path.read_text())

    fresh_lock = Lockfile(generated_from=compute_manifest_hash(manifest))
    (tmp_path / "project.lock").write_text(json.dumps(fresh_lock.model_dump(mode="json")))

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert "no manifest/lock drift detected" in result.output


def test_reports_manifest_lock_drift_when_lock_exists(tmp_path: Path) -> None:
    manifest_path = FIXTURES_DIR / "valid.project.yaml"
    manifest = Manifest.model_validate(yaml.safe_load(manifest_path.read_text()))

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(manifest_path.read_text())

    stale_lock = Lockfile(generated_from="stale-hash-not-matching-current-manifest")
    (tmp_path / "project.lock").write_text(json.dumps(stale_lock.model_dump(mode="json")))

    assert stale_lock.generated_from != compute_manifest_hash(manifest)

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert "drift" in result.output.lower()


def test_drift_detected_against_real_scanned_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`validate` reports `commit_mismatch` drift sourced from a real
    `WorkspaceProvider.scan` -> `materialize_state` pipeline, not a
    hardcoded `materialized=None` (the dead path this PR activates)."""
    manifest_path = FIXTURES_DIR / "valid.project.yaml"
    manifest = Manifest.model_validate(yaml.safe_load(manifest_path.read_text()))

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(manifest_path.read_text())

    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="expected-sha"
                    )
                ],
            ),
        ],
    )
    (tmp_path / "project.lock").write_text(lock.to_canonical_json())

    monkeypatch.setattr(
        main,
        "_make_workspace_provider",
        lambda: _FakeScanningWorkspaceProvider(
            [
                ScannedRepo(
                    path=Path("/mnt/community/core/odoo"),
                    url="https://github.com/odoo/odoo.git",
                    commit="stale-sha",
                )
            ]
        ),
    )

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert "commit_mismatch" not in result.output  # rendered as human text, not the raw kind
    assert "lock declares 'expected-sha' but materialized at 'stale-sha'" in result.output


def test_validate_scans_and_materializes_with_the_resolved_host_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`validate` must thread the resolved HOST mount table — not the fixed
    container table — into `provider.scan`/`materialize_state`."""
    manifest_path = FIXTURES_DIR / "valid.project.yaml"
    manifest = Manifest.model_validate(yaml.safe_load(manifest_path.read_text()))

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(manifest_path.read_text())

    fresh_lock = Lockfile(generated_from=compute_manifest_hash(manifest))
    (tmp_path / "project.lock").write_text(json.dumps(fresh_lock.model_dump(mode="json")))

    base = Path("/custom/state/odoo-forge")
    monkeypatch.setattr(main, "_resolve_mount_base", lambda: base)
    custom_roots = build_mount_roots(base, manifest)

    scan_calls: list[object] = []

    class _RecordingWorkspaceProvider:
        def checkout(self, url: str, commit: str, dest: Path) -> None:
            raise NotImplementedError

        def scan(self, roots: object) -> list[ScannedRepo]:
            scan_calls.append(roots)
            return []

        def promote(self, source: Path, dest: Path, branch: str) -> None:
            raise NotImplementedError

    monkeypatch.setattr(main, "_make_workspace_provider", lambda: _RecordingWorkspaceProvider())

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert scan_calls == [list(custom_roots.values())]
