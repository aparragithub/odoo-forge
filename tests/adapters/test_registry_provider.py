import subprocess

import pytest

from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryImageNotFoundError,
    RegistryPublishError,
    RegistryPullError,
    RegistryUnavailableError,
)
from odoo_forge.image_registry.types import ImageDigestRef, ImageRef
from odoo_forge_registry.provider import GhcrImageRegistryProvider


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_publish_fails_fast_with_transition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess.run must not be called for publish()")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    provider = GhcrImageRegistryProvider()

    with pytest.raises(RegistryPublishError) as exc_info:
        provider.publish(ImageRef("ghcr.io/acme/app:latest"))

    assert exc_info.value.ref == "ghcr.io/acme/app:latest"
    assert exc_info.value.detail == ("publish is not available in this transition adapter")


def test_pull_fails_fast_with_transition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess.run must not be called for pull()")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    provider = GhcrImageRegistryProvider()

    with pytest.raises(RegistryPullError) as exc_info:
        provider.pull(ImageDigestRef("ghcr.io/acme/app@sha256:" + "a" * 64))

    assert exc_info.value.ref == "ghcr.io/acme/app@sha256:" + "a" * 64
    assert exc_info.value.detail == ("pull is not available in this transition adapter")


def test_resolve_digest_delegates_to_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GhcrImageRegistryProvider()
    calls: list[str] = []

    def _fake_resolve(ref: str) -> str:
        calls.append(ref)
        return "ghcr.io/acme/app@sha256:" + "b" * 64

    monkeypatch.setattr(provider, "resolve", _fake_resolve)

    result = provider.resolve_digest(ImageRef("ghcr.io/acme/app:latest"))

    assert calls == ["ghcr.io/acme/app:latest"]
    assert result == ImageDigestRef("ghcr.io/acme/app@sha256:" + "b" * 64)


def test_exists_returns_true_when_validate_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GhcrImageRegistryProvider()

    monkeypatch.setattr(
        provider,
        "validate",
        lambda ref: "ghcr.io/acme/app@sha256:" + "c" * 64,
    )

    assert provider.exists(ImageDigestRef("ghcr.io/acme/app@sha256:" + "c" * 64))


def test_exists_returns_false_when_validate_reports_missing_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = GhcrImageRegistryProvider()

    def _raise_not_found(ref: str) -> str:
        raise RegistryImageNotFoundError(ref)

    monkeypatch.setattr(provider, "validate", _raise_not_found)

    assert not provider.exists(ImageDigestRef("ghcr.io/acme/app@sha256:" + "d" * 64))


def test_exists_propagates_non_not_found_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GhcrImageRegistryProvider()

    def _raise_unavailable(ref: str) -> str:
        raise RegistryUnavailableError(ref, "docker unavailable")

    monkeypatch.setattr(provider, "validate", _raise_unavailable)

    with pytest.raises(RegistryUnavailableError):
        provider.exists(ImageDigestRef("ghcr.io/acme/app@sha256:" + "e" * 64))


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
            stderr=("ERROR: no such manifest: ghcr.io/acme/app@sha256:cccc"),
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
