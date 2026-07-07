from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.manifest.errors import RefNotFoundError
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge_cli import main
from odoo_forge_cli.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

runner = CliRunner()


class _FakeSourceProvider:
    def resolve_ref(self, url: str, ref: str) -> str:
        return f"sha-{ref}"


class _FailingSourceProvider:
    def resolve_ref(self, url: str, ref: str) -> str:
        raise RefNotFoundError(url, ref)


def test_valid_manifest_writes_canonical_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "_make_provider", lambda: _FakeSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    lock_path = tmp_path / "project.lock"
    assert lock_path.exists()

    lock = Lockfile.from_json(lock_path.read_text())
    assert lock.schema_version == 1
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].commit.startswith("sha-")


def test_core_ref_none_resolved_via_default_before_pinning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "_make_provider", lambda: _FakeSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(
        "name: minimal\n"
        "odoo_version: '19.0'\n"
        "edition: community\n"
        "core:\n"
        "  type: core\n"
        "client:\n"
        "  addons_path: client/addons\n"
    )

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    lock = Lockfile.from_json((tmp_path / "project.lock").read_text())
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].ref == "19.0"
    assert core_layer.repos[0].commit == "sha-19.0"


def test_resolution_error_exits_one_with_clean_message_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "_make_provider", lambda: _FailingSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert not (tmp_path / "project.lock").exists()


def test_lock_then_validate_round_trip_no_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "_make_provider", lambda: _FakeSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    lock_result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])
    assert lock_result.exit_code == 0

    validate_result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert validate_result.exit_code == 0
    assert "no manifest/lock drift detected" in validate_result.output


def test_load_lock_uses_from_json_roundtrip(tmp_path: Path) -> None:
    """A lock written via `Lockfile.to_canonical_json()` reads back via `from_json()`."""
    lock = Lockfile(generated_from="deadbeef")
    lock_path = tmp_path / "project.lock"
    lock_path.write_text(lock.to_canonical_json())

    loaded = main._load_lock(lock_path)

    assert loaded is not None
    assert loaded.generated_from == "deadbeef"
    assert loaded.schema_version == lock.schema_version


def test_load_lock_rejects_invalid_json(tmp_path: Path) -> None:
    from odoo_forge.manifest.errors import LockfileError

    lock_path = tmp_path / "project.lock"
    lock_path.write_text("{ not valid json")

    with pytest.raises(LockfileError):
        main._load_lock(lock_path)
