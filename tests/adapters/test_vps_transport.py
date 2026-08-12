"""Hermetic security tests for the provider-private OpenSSH transport."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from odoo_forge_docker.vps.transport import (
    InvalidRemoteInputError,
    MutationState,
    OpenSshTarget,
    OpenSshTransport,
    TransportFailure,
    UnknownMutationOutcomeError,
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

    result = OpenSshTransport(_target(), timeout=7).run(["docker", "inspect", "odoo-1"])

    assert result.stdout == "ready"
    argv = calls[0][0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "UserKnownHostsFile=" in " ".join(argv)
    assert "ConnectTimeout=7" in argv
    assert argv[-1] == "docker inspect odoo-1"


def test_safe_addon_path_value_accepts_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "odoo_forge_docker.vps.transport.subprocess.run",
        lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="ready", stderr=""),
    )

    result = OpenSshTransport(_target()).run(
        ["docker", "run", "--env", "FORGE_ADDONS_PATH_ORDER=/mnt/worktrees,/mnt/community"]
    )

    assert result.stdout == "ready"


def test_changed_host_key_is_safe_pre_mutation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=255,
            stdout="",
            stderr="WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!",
        )

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    with pytest.raises(TransportFailure) as exc_info:
        OpenSshTransport(_target()).run(["docker", "inspect", "odoo-1"], mutating=True)

    assert exc_info.value.state is MutationState.PRE_MUTATION
    assert "REMOTE HOST" not in str(exc_info.value)


def test_secret_upload_uses_private_staging_and_redacts_process_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        source = Path(argv[-2])
        observed["mode"] = os.stat(source).st_mode & 0o777
        observed["exists"] = source.exists()
        observed["argv"] = argv
        return SimpleNamespace(returncode=0, stdout=_SECRET, stderr=f"copied {_SECRET}")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)
    result = OpenSshTransport(_target(), staging_root=tmp_path).upload_secret(
        _SECRET, "/run/secrets/odoo"
    )

    assert observed["mode"] == 0o600
    assert observed["exists"] is True
    assert _SECRET not in result.stdout
    assert _SECRET not in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_timeout_before_mutation_is_safe_and_timeout_during_mutation_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, float)
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)
    transport = OpenSshTransport(_target())

    with pytest.raises(TransportFailure) as safe_info:
        transport.run(["docker", "inspect", "odoo-1"])
    assert safe_info.value.state is MutationState.PRE_MUTATION

    with pytest.raises(UnknownMutationOutcomeError) as unknown_info:
        transport.run(["docker", "rm", "odoo-1"], mutating=True)
    assert unknown_info.value.state is MutationState.UNKNOWN_POST_MUTATION
