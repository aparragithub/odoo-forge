import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml
from typer.testing import CliRunner

from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import _support
from odoo_forge_cli.commands import manifest
from odoo_forge_cli.main import app

runner = CliRunner()


def _invoke_configure(target: Path, *, name: str = "demo", edition: str = "community") -> Any:
    scripted_input = f"{name}\n19.0\n{edition}\n\n\nn\nclient/addons\nn\nn\nn\nn\ny\n"
    return runner.invoke(app, ["configure", "--manifest", str(target)], input=scripted_input)


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


def test_configure_community_yaml(tmp_path: Path) -> None:
    target = tmp_path / "project.yaml"
    result = _invoke_configure(target, name="community-demo")
    expected = Manifest.model_validate(
        {
            "name": "community-demo",
            "odoo_version": "19.0",
            "edition": "community",
            "client": {"addons_path": "client/addons"},
        }
    )

    expected_yaml = """name: community-demo
odoo_version: '19.0'
edition: community
client:
  addons_path: client/addons
"""

    assert target.read_text() == expected_yaml
    assert result.output.endswith(f"created {target}\n")
    assert Manifest.model_validate(yaml.safe_load(target.read_text())) == expected


def test_configure_enterprise_collects_all_optional_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = {
        "Project name": "enterprise-demo",
        "Odoo version": "19.0",
        "Edition": "enterprise",
        "Core URL override": "https://example.test/core.git",
        "Core ref override": "stable",
        "Enterprise URL override": "https://example.test/enterprise.git",
        "Enterprise ref override": "stable",
        "Layer name": "custom",
        "Layer category": "localization",
        "Repository URL": "https://example.test/custom.git",
        "Repository ref": "main",
        "Client addons path": "client/addons",
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


def test_configure_rejects_existing_target_before_prompt(tmp_path: Path) -> None:
    target = tmp_path / "project.yaml"
    target.write_text("original\n")

    result = runner.invoke(app, ["configure", "--manifest", str(target)])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert target.read_text() == "original\n"


def test_configure_invalid_draft_reports_actionable_error_without_write(
    tmp_path: Path,
) -> None:
    target = tmp_path / "project.yaml"
    result = _invoke_configure(target, edition="invalid")

    assert result.exit_code == 1
    assert "error: edition:" in result.output
    assert list(tmp_path.iterdir()) == []


def test_configure_unicode(tmp_path: Path) -> None:
    target = tmp_path / "project.yaml"
    result = _invoke_configure(target, name="café")

    assert result.exit_code == 0
    assert "café" in target.read_text(encoding="utf-8")


def test_configure_publication_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "project.yaml"

    def fail_link(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(_support.os, "link", fail_link)  # type: ignore[attr-defined]
    result = _invoke_configure(target)

    assert result.exit_code == 1
    assert "simulated publication failure" in result.output
    assert list(tmp_path.iterdir()) == []


def test_configure_race_preserves_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "project.yaml"
    original_link = os.link

    def create_target_then_link(source: Path, destination: Path) -> None:
        destination.write_text("racing\n", encoding="utf-8")
        original_link(source, destination)

    monkeypatch.setattr(_support.os, "link", create_target_then_link)  # type: ignore[attr-defined]
    result = _invoke_configure(target)

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert target.read_text(encoding="utf-8") == "racing\n"
    assert list(tmp_path.iterdir()) == [target]
