"""Hermetic security tests for the provider-private OpenSSH transport."""

from types import SimpleNamespace

import pytest

from odoo_forge_docker.vps.transport import (
    InvalidRemoteInputError,
    OpenSshTarget,
    OpenSshTransport,
)

_SECRET = "transport-secret-marker"


def _target() -> OpenSshTarget:
    return OpenSshTarget(
        host="vps.example.test",
        user="forge",
        port=2222,
        host_key="vps.example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIpin",
        private_key=(
            f"-----BEGIN OPENSSH PRIVATE KEY-----\n{_SECRET}\n-----END OPENSSH PRIVATE KEY-----\n"
        ),
    )


def test_rejects_remote_shell_metacharacters_without_invoking_ssh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    with pytest.raises(InvalidRemoteInputError):
        OpenSshTransport(_target()).run(["docker", "inspect", "name;touch /tmp/pwned"])

    assert calls == []


def test_ssh_uses_fixed_argv_batch_mode_and_pinned_host_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((argv, kwargs))
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=0, stdout="ready", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    target = _target()
    result = OpenSshTransport(target, timeout=7).run(["docker", "inspect", "odoo-1"])

    assert result.stdout == "ready"
    argv = calls[0][0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "-F" in argv
    assert "/dev/null" in argv
    assert "GlobalKnownHostsFile=/dev/null" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "UserKnownHostsFile=" in " ".join(argv)
    assert "ConnectTimeout=6" in argv
    assert target.private_key not in argv
    assert argv[-1] == "docker inspect odoo-1"


def test_connect_timeout_is_integer_and_bounded_for_fractional_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    OpenSshTransport(_target(), timeout=7.5).run(["docker", "inspect", "odoo-1"])

    argv, kwargs = calls[0]
    assert "ConnectTimeout=7" in argv
    assert float(argv[argv.index("ConnectTimeout=7")].split("=")[1]).is_integer()
    assert kwargs["timeout"] == 7.5


def test_tiny_timeout_uses_valid_positive_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    OpenSshTransport(_target(), timeout=0.25).run(["docker", "inspect", "odoo-1"])

    assert "ConnectTimeout=1" in calls[0]


def test_safe_addon_path_value_accepts_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "odoo_forge_docker.vps.transport.subprocess.run",
        lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="ready", stderr=""),
    )

    result = OpenSshTransport(_target()).run(
        ["docker", "run", "--env", "FORGE_ADDONS_PATH_ORDER=/mnt/worktrees,/mnt/community"]
    )

    assert result.stdout == "ready"
