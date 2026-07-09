import subprocess

import pytest

from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryImageNotFoundError,
    RegistryUnavailableError,
)
from odoo_forge_registry.provider import GhcrImageRegistryProvider


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_resolve_returns_canonical_digest_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        assert argv == [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            "ghcr.io/acme/app:latest",
            "--format",
            "{{json .}}",
        ]
        return _FakeCompletedProcess(
            0,
            stdout='{"name":"ghcr.io/acme/app:latest","manifest":{"digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}',
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()

    assert provider.resolve("ghcr.io/acme/app:latest") == (
        "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )


def test_validate_returns_same_canonical_digest_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(
            0,
            stdout=(
                '{"manifest":{"digest":'
                '"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}'
            ),
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()
    ref = "ghcr.io/acme/app@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    assert provider.validate(ref) == ref


def test_validate_rejects_digest_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(
            0,
            stdout=(
                '{"manifest":{"digest":'
                '"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}}'
            ),
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()
    ref = "ghcr.io/acme/app@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    with pytest.raises(RegistryImageNotFoundError):
        provider.validate(ref)


def test_resolve_maps_auth_failure_to_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1, stderr="unauthorized: authentication required")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryAuthenticationError) as exc:
        GhcrImageRegistryProvider().resolve("ghcr.io/acme/app:latest")

    assert "ghcr authentication failed" in str(exc.value).lower()


def test_validate_maps_not_found_failure_to_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(
            1,
            stderr=(
                "ERROR: no such manifest: "
                "ghcr.io/acme/app@sha256:cccc"
            ),
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryImageNotFoundError):
        GhcrImageRegistryProvider().validate(
            "ghcr.io/acme/app@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
        )


def test_resolve_rejects_malformed_reference_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(argv)
        return _FakeCompletedProcess(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(MalformedImageReferenceError):
        GhcrImageRegistryProvider().resolve("ghcr.io/acme/app")

    assert calls == []


def test_resolve_maps_timeout_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        timeout = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(
            cmd=list(argv), timeout=timeout if isinstance(timeout, (int, float)) else 30
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryUnavailableError):
        GhcrImageRegistryProvider().resolve("ghcr.io/acme/app:latest")
