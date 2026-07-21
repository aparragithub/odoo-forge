"""`rotate_enterprise_credential`: thin `sops updatekeys` wrapper.

Lives in the docker adapter (alongside `SopsCommandResolver`, the other
`sops`-shelling adapter in this module) because core (`odoo_forge`) is
forbidden from importing `subprocess` — see the "Core never imports
infrastructure or framework" import-linter contract.

Fake resolvers / monkeypatched `subprocess.run` only — never real `sops`.
"""

from pathlib import Path

import pytest

from odoo_forge_docker.credential_injection import rotate_enterprise_credential

_SECRET_MARKER = "s3cr3t-age-doctor-marker"


def test_rotate_enterprise_credential_invokes_sops_updatekeys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials_file = tmp_path / "credentials.sops.yaml"
    recorded_argv: list[str] = []

    class _FakeCompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        recorded_argv.extend(argv)
        return _FakeCompletedProcess()

    monkeypatch.setattr("odoo_forge_docker.credential_injection.subprocess.run", fake_run)

    result = rotate_enterprise_credential(credentials_file=credentials_file)

    assert result.ok is True
    assert recorded_argv[0] == "sops"
    assert "updatekeys" in recorded_argv
    assert str(credentials_file) in recorded_argv


def test_rotate_enterprise_credential_fails_fast_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials_file = tmp_path / "credentials.sops.yaml"

    class _FakeCompletedProcess:
        returncode = 1
        stdout = ""
        stderr = "boom"

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess()

    monkeypatch.setattr("odoo_forge_docker.credential_injection.subprocess.run", fake_run)

    result = rotate_enterprise_credential(credentials_file=credentials_file)

    assert result.ok is False
    assert "sops" in result.message.lower()
    assert not credentials_file.exists()


def test_rotate_enterprise_credential_never_leaks_secret_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials_file = tmp_path / "credentials.sops.yaml"

    class _FakeCompletedProcess:
        returncode = 1
        stdout = f"leaked {_SECRET_MARKER}"
        stderr = f"leaked {_SECRET_MARKER}"

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess()

    monkeypatch.setattr("odoo_forge_docker.credential_injection.subprocess.run", fake_run)

    result = rotate_enterprise_credential(credentials_file=credentials_file)

    assert _SECRET_MARKER not in result.message
