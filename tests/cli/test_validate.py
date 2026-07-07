import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from odoo_forge.manifest.lockfile import Lockfile, compute_manifest_hash
from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

runner = CliRunner()


def test_valid_manifest_exits_zero() -> None:
    result = runner.invoke(app, ["validate", "--manifest", str(FIXTURES_DIR / "valid.project.yaml")])

    assert result.exit_code == 0


def test_malformed_manifest_single_cause_error_nonzero_exit() -> None:
    result = runner.invoke(
        app, ["validate", "--manifest", str(FIXTURES_DIR / "malformed.project.yaml")]
    )

    assert result.exit_code != 0
    assert result.output.count("error:") == 1


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
