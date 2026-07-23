"""`forge doctor`: age-key presence + conventional Enterprise credential
resolution, reported independently. Fake resolver / no real age key file
required — never touches real `sops`/`age`.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.credentials.errors import CredentialUnavailableError
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge_cli import _composition, enterprise_credential
from odoo_forge_cli.main import app

runner = CliRunner()

_SECRET_MARKER = "s3cr3t-doctor-cli-marker"


def _write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(
        "name: doctor-project\n"
        "odoo_version: '19.0'\n"
        "edition: community\n"
        "core:\n"
        "  type: core\n"
        "  url: https://github.com/odoo/odoo.git\n"
        "  ref: '19.0'\n"
        "client:\n"
        "  addons_path: client/addons\n"
    )
    return manifest_path


def _succeeding_resolver(handle: CredentialHandle) -> str:
    return _SECRET_MARKER


def _raising_resolver(handle: CredentialHandle) -> str:
    raise CredentialUnavailableError()


def test_doctor_fails_and_reports_missing_age_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_key_file = tmp_path / "no-such-keys.txt"
    monkeypatch.setattr(
        enterprise_credential,
        "_make_enterprise_credential_resolver",
        lambda **kwargs: _succeeding_resolver,
    )
    monkeypatch.setattr(_composition, "_doctor_age_key_file", lambda: missing_key_file)
    manifest_path = _write_manifest(tmp_path)

    result = runner.invoke(app, ["doctor", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert "age-key" in result.output
    assert "FAIL" in result.output
    assert "enterprise-credential" in result.output
    assert "ok" in result.output


def test_doctor_fails_and_reports_missing_enterprise_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "keys.txt"
    key_file.write_text(
        "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQ\n"
    )
    monkeypatch.setattr(
        enterprise_credential,
        "_make_enterprise_credential_resolver",
        lambda **kwargs: _raising_resolver,
    )
    monkeypatch.setattr(_composition, "_doctor_age_key_file", lambda: key_file)
    manifest_path = _write_manifest(tmp_path)

    result = runner.invoke(app, ["doctor", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert "enterprise-credential" in result.output
    assert "FAIL" in result.output


def test_doctor_reports_success_on_both_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "keys.txt"
    key_file.write_text(
        "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQ\n"
    )
    monkeypatch.setattr(
        enterprise_credential,
        "_make_enterprise_credential_resolver",
        lambda **kwargs: _succeeding_resolver,
    )
    monkeypatch.setattr(_composition, "_doctor_age_key_file", lambda: key_file)
    manifest_path = _write_manifest(tmp_path)

    result = runner.invoke(app, ["doctor", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    assert "ok" in result.output
    assert "FAIL" not in result.output
    assert _SECRET_MARKER not in result.output
    assert "Traceback" not in result.output
