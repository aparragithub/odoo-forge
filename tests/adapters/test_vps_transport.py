"""Hermetic security tests for the provider-private OpenSSH transport."""

from types import SimpleNamespace

import pytest

from odoo_forge_docker.vps.transport import (
    InvalidRemoteInputError,
    MutationState,
    OpenSshTarget,
    OpenSshTransport,
    TransportFailure,
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
