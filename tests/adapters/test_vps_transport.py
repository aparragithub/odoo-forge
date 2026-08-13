"""Hermetic security tests for the provider-private OpenSSH transport."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest

from odoo_forge_docker.vps.transport import (
    CommandResult,
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


@pytest.mark.parametrize(
    "token",
    [
        "--env=FORGE_PASSWORD=transport-password-marker",
        "-eFORGE_API_TOKEN=transport-token-marker",
    ],
)
def test_rejects_inline_secret_assignments_before_ssh_argv(
    token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    with pytest.raises(InvalidRemoteInputError):
        OpenSshTransport(_target()).run(["docker", "run", token])

    assert calls == []


@pytest.mark.parametrize(
    "token",
    [
        "--env=FORGE_ADDONS_PATH_ORDER=/mnt/worktrees,/mnt/community",
        "--env=POSTGRES_PASSWORD_FILE=/run/secrets/postgres",
    ],
)
def test_accepts_safe_inline_environment_assignments(
    token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="ready", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    result = OpenSshTransport(_target()).run(["docker", "run", token])

    assert result.stdout == "ready"
    assert calls[0][-1].endswith(token)


@pytest.mark.parametrize(
    "assignment",
    [
        "FORGE_PASSWORD=transport-password-marker",
        "FORGE_API_TOKEN=transport-token-marker",
        "FORGE_SECRET=transport-secret-marker",
    ],
)
def test_rejects_secret_assignments_before_ssh_argv(
    assignment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    with pytest.raises(InvalidRemoteInputError):
        OpenSshTransport(_target()).run(["docker", "run", "--env", assignment])

    assert calls == []


def test_secret_file_assignment_remains_safe_for_provider_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="ready", stderr="")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    result = OpenSshTransport(_target()).run(
        ["docker", "run", "--env", "POSTGRES_PASSWORD_FILE=/run/secrets/postgres"]
    )

    assert result.stdout == "ready"
    assert calls[0][-1].endswith("POSTGRES_PASSWORD_FILE=/run/secrets/postgres")


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
    argv = observed["argv"]
    assert isinstance(argv, list)
    assert _SECRET not in argv
    assert _target().private_key not in argv
    assert "GlobalKnownHostsFile=/dev/null" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "ConnectTimeout=29" in argv
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


def test_mutating_failure_never_exposes_secret_or_raw_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=255, stdout="", stderr=f"failed {_SECRET}")

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    with pytest.raises(UnknownMutationOutcomeError) as exc_info:
        OpenSshTransport(_target()).run(["docker", "rm", "odoo-1"], mutating=True)

    assert _SECRET not in str(exc_info.value)
    assert "failed transport" not in str(exc_info.value)


def test_remote_non_255_failure_is_a_command_result_even_with_transport_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=17,
            stdout="remote stdout",
            stderr="connection refused: application command rejected",
        )

    monkeypatch.setattr("odoo_forge_docker.vps.transport.subprocess.run", fake_run)

    result = OpenSshTransport(_target()).run(["docker", "inspect", "odoo-1"], mutating=True)

    assert isinstance(result, CommandResult)
    assert result.returncode == 17
    assert result.stdout == "remote stdout"
    assert result.stderr == "connection refused: application command rejected"


@pytest.mark.parametrize(
    ("failure", "message"),
    [("write", "write failed"), ("close", "close failed")],
)
def test_secret_upload_stream_owns_fd_after_write_or_close_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    message: str,
) -> None:
    raw_close_calls: list[int] = []
    stream_close_calls: list[int] = []
    secret_fd = 41
    real_open = os.open
    real_fdopen = os.fdopen
    real_close = os.close

    class FailingStream:
        def __enter__(self) -> "FailingStream":
            return self

        def __exit__(self, *args: object) -> Literal[False]:
            self.close()
            return False

        def write(self, value: str) -> None:
            if failure == "write":
                raise OSError("write failed")

        def close(self) -> None:
            stream_close_calls.append(secret_fd)
            if failure == "close":
                raise OSError("close failed")

    stream = FailingStream()
    monkeypatch.setattr(
        "odoo_forge_docker.vps.transport.os.open",
        lambda path, *args, **kwargs: (
            secret_fd if Path(path).name == "secret" else real_open(path, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(
        "odoo_forge_docker.vps.transport.os.fdopen",
        lambda fd, *args, **kwargs: stream if fd == secret_fd else real_fdopen(fd, *args, **kwargs),
    )

    def observe_close(fd: int) -> None:
        if fd == secret_fd:
            raw_close_calls.append(fd)
        else:
            real_close(fd)

    monkeypatch.setattr("odoo_forge_docker.vps.transport.os.close", observe_close)

    with pytest.raises(OSError, match=message):
        OpenSshTransport(_target(), staging_root=tmp_path).upload_secret(
            "secret", "/run/secrets/odoo"
        )

    assert stream_close_calls == [secret_fd]
    assert raw_close_calls == []
