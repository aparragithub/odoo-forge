import subprocess
import traceback

import pytest

from odoo_forge.image_registry import ImageDigestRef, ImageRef
from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryDigestMismatchError,
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


SECRET_REF = "token-user:super-secret@ghcr.io/acme/app:latest"
SAFE_REPOSITORY = "ghcr.io/acme/app"


def _assert_public_exception_is_safe(error: BaseException) -> None:
    public_values = [str(error), repr(error), repr(error.args)]
    public_values.extend(repr(value) for value in vars(error).values())
    public_values.append("".join(traceback.format_exception(error)))
    if error.__cause__ is not None:
        public_values.extend((str(error.__cause__), repr(error.__cause__)))
    if error.__context__ is not None:
        public_values.extend((str(error.__context__), repr(error.__context__)))
    rendered = "\n".join(public_values)
    assert "token-user" not in rendered
    assert "super-secret" not in rendered
    assert SECRET_REF not in rendered
    assert "secret stderr" not in rendered


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


@pytest.mark.parametrize("operation", ["publish", "resolve_digest"])
def test_tag_operations_reject_credential_bearing_refs_without_leaking(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("credentials must be rejected before subprocess"),
    )

    with pytest.raises(MalformedImageReferenceError) as exc_info:
        getattr(GhcrImageRegistryProvider(), operation)(ImageRef(SECRET_REF))

    assert SAFE_REPOSITORY in str(exc_info.value)
    _assert_public_exception_is_safe(exc_info.value)


@pytest.mark.parametrize("operation", ["pull", "exists"])
def test_digest_operations_reject_credential_bearing_refs_without_leaking(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    digest_ref = SECRET_REF.replace(":latest", "@sha256:" + "a" * 64)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("credentials must be rejected before subprocess"),
    )

    with pytest.raises(MalformedImageReferenceError) as exc_info:
        getattr(GhcrImageRegistryProvider(), operation)(ImageDigestRef(digest_ref))

    assert SAFE_REPOSITORY in str(exc_info.value)
    _assert_public_exception_is_safe(exc_info.value)


def test_authentication_marker_wins_over_not_found_and_hides_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            1, stderr="manifest unknown; unauthorized; secret stderr token=super-secret"
        ),
    )

    with pytest.raises(RegistryAuthenticationError) as exc_info:
        GhcrImageRegistryProvider().resolve_digest(ImageRef("ghcr.io/acme/app:latest"))

    _assert_public_exception_is_safe(exc_info.value)


def test_publish_nested_error_chain_is_credential_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            1, stderr="unauthorized: secret stderr token=super-secret"
        ),
    )

    with pytest.raises(RegistryPublishError) as exc_info:
        GhcrImageRegistryProvider().publish(ImageRef("ghcr.io/acme/app:latest"))

    assert isinstance(exc_info.value.__cause__, RegistryAuthenticationError)
    assert SAFE_REPOSITORY in str(exc_info.value)
    _assert_public_exception_is_safe(exc_info.value)


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


@pytest.mark.parametrize(
    ("stderr", "error_type"),
    [
        ("unauthorized: manifest unknown", RegistryAuthenticationError),
        ("registry service unavailable: secret stderr", RegistryUnavailableError),
    ],
)
def test_exists_propagates_non_not_found_failures(
    stderr: str, error_type: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompletedProcess(1, stderr=stderr),
    )

    with pytest.raises(error_type) as exc_info:
        GhcrImageRegistryProvider().exists(ImageDigestRef("ghcr.io/acme/app@sha256:" + "f" * 64))

    _assert_public_exception_is_safe(exc_info.value)


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


def test_exists_raises_safe_integrity_error_when_inspected_digest_differs(
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

    with pytest.raises(RegistryDigestMismatchError) as exc_info:
        provider.exists(
            ImageDigestRef(
                "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        )

    assert exc_info.value.ref == SAFE_REPOSITORY
    assert "digest mismatch" in str(exc_info.value)
    _assert_public_exception_is_safe(exc_info.value)
    assert "a" * 64 not in str(exc_info.value)
    assert "b" * 64 not in str(exc_info.value)


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


@pytest.mark.parametrize("failure", ["timeout", "missing-binary"])
def test_subprocess_exceptions_are_safe_and_contract_is_preserved(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "super-" + "secret"
    secret_error = "secret " + "stderr"

    def _fake_run(argv: list[str], **kwargs: object) -> None:
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 7.5
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["LANG"] == "C"
        assert env["LC_ALL"] == "C"
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                cmd=[*argv, SECRET_REF],
                timeout=7.5,
                output=secret,
                stderr=secret_error,
            )
        raise FileNotFoundError(2, secret_error, SECRET_REF)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RegistryUnavailableError) as exc_info:
        GhcrImageRegistryProvider(timeout=7.5).resolve_digest(ImageRef("ghcr.io/acme/app:latest"))

    assert SAFE_REPOSITORY in str(exc_info.value)
    _assert_public_exception_is_safe(exc_info.value)


@pytest.mark.parametrize("operation", ["resolve_digest", "publish", "pull"])
def test_all_docker_operations_share_subprocess_and_canonical_digest_contract(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    digest = "sha256:" + "d" * 64
    digest_ref = f"ghcr.io/acme/app@{digest}"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 4.25
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["LANG"] == "C"
        assert env["LC_ALL"] == "C"
        if argv[:2] == ["docker", "push"]:
            return _FakeCompletedProcess(0, stderr=f"latest: digest: {digest} size: 1")
        if argv[:2] == ["docker", "pull"]:
            return _FakeCompletedProcess(0)
        return _FakeCompletedProcess(0, stdout=f'{{"manifest":{{"digest":"{digest}"}}}}')

    monkeypatch.setattr(subprocess, "run", _fake_run)
    provider = GhcrImageRegistryProvider(timeout=4.25)

    if operation == "pull":
        assert provider.pull(ImageDigestRef(digest_ref)) == digest_ref
    else:
        assert getattr(provider, operation)(ImageRef("ghcr.io/acme/app:latest")) == digest_ref
