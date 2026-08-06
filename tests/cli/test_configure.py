from collections.abc import Mapping
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import _support
from odoo_forge_cli.commands import manifest
from odoo_forge_cli.main import app

runner = CliRunner()


def _script(
    monkeypatch: pytest.MonkeyPatch,
    prompts: Mapping[str, object],
    confirms: Mapping[str, object],
) -> None:
    def prompt(message: str, **_: object) -> object:
        for key, value in prompts.items():
            if message.startswith(key):
                return value.pop(0) if isinstance(value, list) else value
        raise AssertionError(f"unexpected prompt: {message}")

    def confirm(message: str, **_: object) -> bool:
        for key, value in confirms.items():
            if message.startswith(key):
                if isinstance(value, list):
                    return bool(value.pop(0))
                return bool(value)
        raise AssertionError(f"unexpected confirmation: {message}")

    monkeypatch.setattr(manifest.typer, "prompt", prompt)  # type: ignore[attr-defined]
    monkeypatch.setattr(manifest.typer, "confirm", confirm)  # type: ignore[attr-defined]


def test_configure_community_previews_exact_yaml_and_creates_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "project.yaml"
    _script(
        monkeypatch,
        {
            "Project name": "community-demo",
            "Odoo version": "19.0",
            "Edition": "community",
            "Core URL override": "",
            "Core ref override": "",
            "Client addons path": "client/addons",
            "Python requirements path": "",
        },
        {
            "Add a layer": False,
            "Add an override": False,
            "Configure workspace": False,
            "Configure backend": False,
            "Add mount priority": False,
            "Create this project.yaml": True,
        },
    )

    manifest.configure(target)

    expected = Manifest.model_validate(
        {
            "name": "community-demo",
            "odoo_version": "19.0",
            "edition": "community",
            "client": {"addons_path": "client/addons"},
        }
    )
    assert target.read_text() == _support.serialize_manifest(expected)
    output = capsys.readouterr().out
    assert output.endswith(_support.serialize_manifest(expected) + "created " + str(target) + "\n")
    assert Manifest.model_validate(yaml.safe_load(target.read_text())) == expected


def test_configure_enterprise_collects_all_optional_branches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompts = {
        "Project name": "enterprise-demo",
        "Odoo version": "19.0",
        "Edition": "enterprise",
        "Core URL override": "https://example.test/core.git",
        "Core ref override": "stable",
        "Enterprise URL override": "https://example.test/enterprise.git",
        "Enterprise ref override": "stable",
        "Layer type": ["unsupported", "git", "published"],
        "Layer name": "custom",
        "Layer category": "localization",
        "Repository URL": "https://example.test/custom.git",
        "Repository ref": "main",
        "Published layer name": "published",
        "Published layer source": "registry://example/addons",
        "Published layer version": "1.0",
        "Published layer category": "enterprise-addons",
        "Client addons path": "client/addons",
        "Python requirements path": "client/requirements.txt",
        "Override layer": "custom",
        "Override repository": "https://example.test/custom.git",
        "Override fork": "https://example.test/fork.git",
        "Override ref": "feature",
        "Workspace checkout timeout": "300",
        "Odoo HTTP port": "18069",
        "Odoo bind host": "127.0.0.1",
        "Mount priority root": "custom/localization",
    }
    confirms = {
        "Add a layer": True,
        "Add another repository": False,
        "Add another layer": [True, False],
        "Published layer requires enterprise": True,
        "Add another override": False,
        "Add an override": True,
        "Configure workspace": True,
        "Configure backend": True,
        "Add mount priority": True,
        "Add another mount priority": False,
        "Create this project.yaml": False,
    }
    _script(monkeypatch, prompts, confirms)

    with pytest.raises(typer.Exit) as raised:
        manifest.configure(Path("project.yaml"))

    assert raised.value.exit_code == 0
    assert "layer type must be 'git' or 'published'" in capsys.readouterr().err


def test_configure_rejects_existing_target_before_prompt(tmp_path: Path) -> None:
    target = tmp_path / "project.yaml"
    target.write_text("original\n")

    result = runner.invoke(app, ["configure", "--manifest", str(target)])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert target.read_text() == "original\n"


def test_configure_invalid_draft_reports_actionable_error_without_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "project.yaml"
    _script(
        monkeypatch,
        {
            "Project name": "invalid-demo",
            "Odoo version": "19.0",
            "Edition": "not-an-edition",
            "Core URL override": "",
            "Core ref override": "",
            "Client addons path": "client/addons",
            "Python requirements path": "",
        },
        {
            "Add a layer": False,
            "Add an override": False,
            "Configure workspace": False,
            "Configure backend": False,
            "Add mount priority": False,
        },
    )

    with pytest.raises(typer.Exit) as raised:
        manifest.configure(target)

    assert raised.value.exit_code == 1
    assert "error: edition:" in capsys.readouterr().err
    assert not target.exists()


def test_create_only_writer_cleans_temporary_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "project.yaml"

    def fail_link(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(_support.os, "link", fail_link)  # type: ignore[attr-defined]

    with pytest.raises(OSError, match="simulated publication failure"):
        _support._write_manifest_create_only(target, "name: demo\n")

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_create_only_writer_preserves_racing_target(tmp_path: Path) -> None:
    target = tmp_path / "project.yaml"
    target.write_text("racing\n")

    with pytest.raises(FileExistsError):
        _support._write_manifest_create_only(target, "name: replacement\n")

    assert target.read_text() == "racing\n"
    assert list(tmp_path.iterdir()) == [target]
