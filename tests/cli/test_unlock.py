from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.manifest.errors import AlreadyUnlockedError
from odoo_forge_cli import main
from odoo_forge_cli.main import app

runner = CliRunner()

_MANIFEST_TEXT = (
    "name: odoo-idp\n"
    "odoo_version: '19.0'\n"
    "edition: community\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "layers:\n"
    "  - type: git\n"
    "    name: custom-x\n"
    "    repos:\n"
    "      - url: https://example.com/custom-x.git\n"
    "        ref: main\n"
    "client:\n"
    "  addons_path: client/addons\n"
)


class _FakeWorkspaceProvider:
    """Records `promote` calls in order, no I/O."""

    def __init__(self, already_unlocked: bool = False) -> None:
        self.promote_calls: list[tuple[Path, Path, str]] = []
        self._already_unlocked = already_unlocked

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        raise NotImplementedError

    def scan(self, roots: object) -> list[object]:
        raise NotImplementedError

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        if self._already_unlocked:
            raise AlreadyUnlockedError(f"'{dest}' is already a writable checkout")
        self.promote_calls.append((source, dest, branch))


def _write_manifest(tmp_path: Path) -> Path:
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(_MANIFEST_TEXT)
    return project_yaml


def test_unlock_succeeds_and_prints_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        [
            "unlock",
            "--manifest",
            str(project_yaml),
            "--layer",
            "custom-x",
            "--repo",
            "https://example.com/custom-x.git",
        ],
    )

    assert result.exit_code == 0
    assert len(fake_provider.promote_calls) == 1
    source, dest, branch = fake_provider.promote_calls[0]
    assert source == Path("/mnt/custom/custom-x/custom-x")
    assert dest == Path("/mnt/worktrees/custom-x/custom-x")
    assert branch in result.output


def test_unlock_core_layer_computes_community_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        [
            "unlock",
            "--manifest",
            str(project_yaml),
            "--layer",
            "core",
            "--repo",
            "https://github.com/odoo/odoo.git",
        ],
    )

    assert result.exit_code == 0
    source, dest, _branch = fake_provider.promote_calls[0]
    assert source == Path("/mnt/community/core/odoo")
    assert dest == Path("/mnt/worktrees/core/odoo")


def test_already_unlocked_exits_nonzero_single_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider(already_unlocked=True)
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        [
            "unlock",
            "--manifest",
            str(project_yaml),
            "--layer",
            "custom-x",
            "--repo",
            "https://example.com/custom-x.git",
        ],
    )

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


def test_unlock_unknown_layer_exits_clean_one_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        [
            "unlock",
            "--manifest",
            str(project_yaml),
            "--layer",
            "does-not-exist",
            "--repo",
            "https://example.com/whatever.git",
        ],
    )

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert not fake_provider.promote_calls
