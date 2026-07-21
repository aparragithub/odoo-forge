"""`forge rotate-enterprise-credential`: thin `sops updatekeys` wrapper for
the conventional entry. Monkeypatched `subprocess.run` only — never real
`sops`. Asserts no schema/state file is touched.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge_cli.main import app

runner = CliRunner()

_SECRET_MARKER = "s3cr3t-rotation-cli-marker"

_MANIFEST_TEXT = (
    "name: rotate-project\n"
    "odoo_version: '19.0'\n"
    "edition: community\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "client:\n"
    "  addons_path: client/addons\n"
)


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(_MANIFEST_TEXT)
    return manifest_path


def test_rotate_enterprise_credential_invokes_sops_updatekeys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_argv: list[str] = []

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        recorded_argv.extend(argv)
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr("odoo_forge_docker.credential_injection.subprocess.run", fake_run)
    manifest_path = _write_manifest(tmp_path)
    (tmp_path / "project.lock").write_text("untouched")

    result = runner.invoke(app, ["rotate-enterprise-credential", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    assert recorded_argv[0] == "sops"
    assert "updatekeys" in recorded_argv
    assert str(tmp_path / "credentials.sops.yaml") in recorded_argv
    assert (tmp_path / "project.lock").read_text() == "untouched"
    assert "Traceback" not in result.output


def test_rotate_enterprise_credential_fails_fast_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(returncode=1, stdout=_SECRET_MARKER, stderr=_SECRET_MARKER)

    monkeypatch.setattr("odoo_forge_docker.credential_injection.subprocess.run", fake_run)
    manifest_path = _write_manifest(tmp_path)

    result = runner.invoke(app, ["rotate-enterprise-credential", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert _SECRET_MARKER not in result.output
    assert "Traceback" not in result.output
