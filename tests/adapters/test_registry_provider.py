import subprocess

import pytest

from odoo_forge.image_registry import ImageDigestRef, ImageRef
from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryImageNotFoundError,
    RegistryPublishError,
    RegistryPullError,
    RegistryUnavailableError,
)
from odoo_forge.ports.image_registry_provider import ImageRegistryProvider
from odoo_forge_registry.provider import GhcrImageRegistryProvider


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_provider_satisfies_image_registry_protocol() -> None:
    assert isinstance(GhcrImageRegistryProvider(), ImageRegistryProvider)


def test_provider_does_not_expose_legacy_resolve_validate_bridge() -> None:
    provider = GhcrImageRegistryProvider()

    assert not hasattr(provider, "resolve")
    assert not hasattr(provider, "validate")


def test_resolve_digest_returns_canonical_digest_ref(monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert provider.resolve_digest(ImageRef("ghcr.io/acme/app:latest")) == (
        "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )


def test_publish_pushes_then_returns_canonical_digest_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        if argv[:2] == ["docker", "push"]:
            return _FakeCompletedProcess(
                0,
                stdout="pushing layers\n",
                stderr=(
                    "latest: digest: "
                    "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd "
                    "size: 1234\n"
                    "finished\n"
                ),
            )
        raise AssertionError(f"unexpected docker invocation: {argv}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()

    assert provider.publish(ImageRef("ghcr.io/acme/app:latest")) == (
        "ghcr.io/acme/app@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
    )
    assert calls == [["docker", "push", "ghcr.io/acme/app:latest"]]


def test_publish_maps_push_failure_to_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1, stderr="unauthorized: authentication required")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryPublishError) as exc_info:
        GhcrImageRegistryProvider().publish(ImageRef("ghcr.io/acme/app:latest"))

    assert "ghcr authentication failed" in str(exc_info.value).lower()


def test_publish_falls_back_to_inspect_when_push_output_lacks_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        if argv[:2] == ["docker", "push"]:
            return _FakeCompletedProcess(0, stdout="pushed successfully\n")
        if argv[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            return _FakeCompletedProcess(
                0,
                stdout=(
                    '{"name":"ghcr.io/acme/app:latest","manifest":'
                    '{"digest":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                    'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}}'
                ),
            )
        raise AssertionError(f"unexpected docker invocation: {argv}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()

    assert provider.publish(ImageRef("ghcr.io/acme/app:latest")) == (
        "ghcr.io/acme/app@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    )
    assert calls == [
        ["docker", "push", "ghcr.io/acme/app:latest"],
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            "ghcr.io/acme/app:latest",
            "--format",
            "{{json .}}",
        ],
    ]


def test_pull_prefetches_digest_and_returns_local_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        if argv[:2] == ["docker", "pull"]:
            return _FakeCompletedProcess(0, stdout="pulled")
        raise AssertionError(f"unexpected docker invocation: {argv}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()
    ref = "ghcr.io/acme/app@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

    assert provider.pull(ImageDigestRef(ref)) == ref
    assert calls == [["docker", "pull", ref]]


def test_pull_maps_failure_to_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1, stderr="manifest unknown")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryPullError) as exc_info:
        GhcrImageRegistryProvider().pull(ImageDigestRef("ghcr.io/acme/app@sha256:" + "e" * 64))

    assert "image reference not found in registry" in str(exc_info.value)


def test_resolve_digest_returns_same_canonical_digest_ref(monkeypatch: pytest.MonkeyPatch) -> None:
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
    ref = "ghcr.io/acme/app:latest"

    assert provider.resolve_digest(ImageRef(ref)) == (
        "ghcr.io/acme/app@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )


def test_exists_reports_absent_digest_without_pulling_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        return _FakeCompletedProcess(
            1, stderr="ERROR: no such manifest: ghcr.io/acme/app@sha256:ffff"
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()

    assert (
        provider.exists(
            ImageDigestRef(
                "ghcr.io/acme/app@sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
            )
        )
        is False
    )
    assert calls == [
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            "ghcr.io/acme/app@sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "--format",
            "{{json .}}",
        ]
    ]


def test_exists_reports_present_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        return _FakeCompletedProcess(
            0,
            stdout=(
                '{"manifest":{"digest":'
                '"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}'
            ),
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GhcrImageRegistryProvider()

    assert (
        provider.exists(
            ImageDigestRef(
                "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        )
        is True
    )
    assert calls == [
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--format",
            "{{json .}}",
        ]
    ]


def test_exists_returns_false_when_inspected_digest_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    assert (
        provider.exists(
            ImageDigestRef(
                "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        )
        is False
    )


def test_resolve_digest_rejects_digest_reference_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        return _FakeCompletedProcess(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(MalformedImageReferenceError):
        GhcrImageRegistryProvider().resolve_digest(
            ImageRef(
                "ghcr.io/acme/app@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            )
        )

    assert calls == []


def test_resolve_digest_maps_auth_failure_to_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(1, stderr="unauthorized: authentication required")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryAuthenticationError) as exc:
        GhcrImageRegistryProvider().resolve_digest(ImageRef("ghcr.io/acme/app:latest"))

    assert "ghcr authentication failed" in str(exc.value).lower()


def test_resolve_digest_maps_not_found_failure_to_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(
            1,
            stderr=("ERROR: no such manifest: ghcr.io/acme/app@sha256:cccc"),
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryImageNotFoundError):
        GhcrImageRegistryProvider().resolve_digest(ImageRef("ghcr.io/acme/app:latest"))


def test_resolve_digest_rejects_malformed_reference_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(argv)
        return _FakeCompletedProcess(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(MalformedImageReferenceError):
        GhcrImageRegistryProvider().resolve_digest(ImageRef("ghcr.io/acme/app"))

    assert calls == []


def test_resolve_maps_timeout_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        timeout = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(
            cmd=list(argv), timeout=timeout if isinstance(timeout, (int, float)) else 30
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryUnavailableError):
        GhcrImageRegistryProvider().resolve_digest(ImageRef("ghcr.io/acme/app:latest"))
