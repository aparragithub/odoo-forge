from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.image_registry.errors import (
    RegistryAuthenticationError,
    RegistryImageNotFoundError,
)
from odoo_forge_cli import _composition
from odoo_forge_cli.main import app

runner = CliRunner()


class _FakeImageRegistryProvider:
    def __init__(
        self,
        *,
        published_ref: str = "ghcr.io/acme/widget@sha256:" + "a" * 64,
        pulled_ref: str = "ghcr.io/acme/widget@sha256:" + "b" * 64,
        resolved_ref: str = "ghcr.io/acme/widget@sha256:" + "c" * 64,
        exists_value: bool = True,
        publish_error: Exception | None = None,
        pull_error: Exception | None = None,
        resolve_digest_error: Exception | None = None,
        exists_error: Exception | None = None,
    ) -> None:
        self.publish_calls: list[str] = []
        self.pull_calls: list[str] = []
        self.resolve_calls: list[str] = []
        self.exists_calls: list[str] = []
        self._published_ref = published_ref
        self._pulled_ref = pulled_ref
        self._resolved_ref = resolved_ref
        self._exists_value = exists_value
        self._publish_error = publish_error
        self._pull_error = pull_error
        self._resolve_digest_error = resolve_digest_error
        self._exists_error = exists_error

    def publish(self, ref: str) -> str:
        self.publish_calls.append(ref)
        if self._publish_error is not None:
            raise self._publish_error
        return self._published_ref

    def pull(self, digest: str) -> str:
        self.pull_calls.append(digest)
        if self._pull_error is not None:
            raise self._pull_error
        return self._pulled_ref

    def resolve_digest(self, ref: str) -> str:
        self.resolve_calls.append(ref)
        if self._resolve_digest_error is not None:
            raise self._resolve_digest_error
        return self._resolved_ref

    def exists(self, digest: str) -> bool:
        self.exists_calls.append(digest)
        if self._exists_error is not None:
            raise self._exists_error
        return self._exists_value

    def resolve(self, ref: str) -> str:
        raise AssertionError("legacy resolve() must not be used")

    def validate(self, ref: str) -> str:
        raise AssertionError("legacy validate() must not be used")


def test_image_resolve_prints_canonical_digest_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider(
        resolved_ref="ghcr.io/acme/widget@sha256:" + "c" * 64
    )
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, ["image-resolve", "--ref", "ghcr.io/acme/widget:latest"])

    assert result.exit_code == 0
    assert result.output.strip() == "ghcr.io/acme/widget@sha256:" + "c" * 64
    assert fake_provider.resolve_calls == ["ghcr.io/acme/widget:latest"]


def test_image_publish_prints_digest_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakeImageRegistryProvider(
        published_ref="ghcr.io/acme/widget@sha256:" + "d" * 64
    )
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, ["image-publish", "--ref", "ghcr.io/acme/widget:latest"])

    assert result.exit_code == 0
    assert result.output.strip() == "ghcr.io/acme/widget@sha256:" + "d" * 64
    assert fake_provider.publish_calls == ["ghcr.io/acme/widget:latest"]


def test_image_publish_rejects_digest_refs_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider()
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        ["image-publish", "--ref", "ghcr.io/acme/widget@sha256:" + "d" * 64],
    )

    assert result.exit_code == 1
    assert "publishable" in result.output.lower()
    assert fake_provider.publish_calls == []


def test_image_pull_prints_local_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakeImageRegistryProvider(pulled_ref="ghcr.io/acme/widget@sha256:" + "e" * 64)
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        ["image-pull", "--ref", "ghcr.io/acme/widget@sha256:" + "e" * 64],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "ghcr.io/acme/widget@sha256:" + "e" * 64
    assert fake_provider.pull_calls == ["ghcr.io/acme/widget@sha256:" + "e" * 64]


def test_image_exists_prints_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakeImageRegistryProvider(exists_value=False)
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        ["image-exists", "--ref", "ghcr.io/acme/widget@sha256:" + "f" * 64],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "false"
    assert fake_provider.exists_calls == ["ghcr.io/acme/widget@sha256:" + "f" * 64]


@pytest.mark.parametrize(
    ("command", "ref", "error", "expected_text"),
    [
        (
            "image-resolve",
            "ghcr.io/acme/widget:latest",
            RegistryAuthenticationError("ghcr.io/acme/widget:latest"),
            "GHCR authentication failed",
        ),
        (
            "image-publish",
            "ghcr.io/acme/widget:latest",
            RegistryAuthenticationError("ghcr.io/acme/widget:latest"),
            "GHCR authentication failed",
        ),
        (
            "image-pull",
            "ghcr.io/acme/widget@sha256:" + "d" * 64,
            RegistryImageNotFoundError("ghcr.io/acme/widget@sha256:" + "d" * 64),
            "image reference not found in registry",
        ),
        (
            "image-exists",
            "ghcr.io/acme/widget@sha256:" + "d" * 64,
            RegistryImageNotFoundError("ghcr.io/acme/widget@sha256:" + "d" * 64),
            "image reference not found in registry",
        ),
    ],
)
def test_image_commands_render_single_cause_registry_errors(
    command: str,
    ref: str,
    error: Exception,
    expected_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider(
        resolve_digest_error=error if command == "image-resolve" else None,
        publish_error=error if command == "image-publish" else None,
        pull_error=error if command == "image-pull" else None,
        exists_error=error if command == "image-exists" else None,
    )
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, [command, "--ref", ref])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert expected_text in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("command", "ref"),
    [
        ("image-resolve", "docker.io/acme/widget:latest"),
        ("image-publish", "ghcr.io/acme/widget"),
        ("image-pull", "ghcr.io/acme/widget:not-a-digest"),
        ("image-exists", "ghcr.io/acme/widget:not-a-digest"),
    ],
)
def test_image_commands_fail_fast_on_usage_boundary_errors(
    command: str,
    ref: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider()
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, [command, "--ref", ref])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert fake_provider.publish_calls == []
    assert fake_provider.pull_calls == []
    assert fake_provider.resolve_calls == []
    assert fake_provider.exists_calls == []


def test_image_exists_reports_present_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider(exists_value=True)
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        ["image-exists", "--ref", "ghcr.io/acme/widget@sha256:" + "e" * 64],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "true"
    assert fake_provider.exists_calls == ["ghcr.io/acme/widget@sha256:" + "e" * 64]


@pytest.mark.parametrize(
    ("command", "ref"),
    [
        ("image-resolve", "ghcr.io/acme/widget:latest"),
        ("image-publish", "ghcr.io/acme/widget:latest"),
        ("image-pull", "ghcr.io/acme/widget@sha256:" + "b" * 64),
        ("image-exists", "ghcr.io/acme/widget@sha256:" + "f" * 64),
    ],
)
def test_registry_commands_do_not_invoke_backend_provider(
    command: str,
    ref: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider()

    def _fail_backend_provider() -> object:
        raise AssertionError("backend provider must not be built")

    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)
    monkeypatch.setattr(_composition, "_make_backend_provider", _fail_backend_provider)

    result = runner.invoke(app, [command, "--ref", ref])

    assert result.exit_code == 0
    assert "Traceback" not in result.output


def test_successful_registry_commands_leave_project_lock_untouched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_provider = _FakeImageRegistryProvider(
        published_ref="ghcr.io/acme/widget@sha256:" + "d" * 64
    )
    monkeypatch.setattr(_composition, "_make_image_registry_provider", lambda: fake_provider)
    monkeypatch.chdir(tmp_path)

    lock_path = tmp_path / "project.lock"
    lock_path.write_text("sentinel-lock\n")

    first_result = runner.invoke(
        app,
        ["image-publish", "--ref", "ghcr.io/acme/widget:latest"],
    )

    assert first_result.exit_code == 0
    assert lock_path.read_text() == "sentinel-lock\n"

    lock_path.unlink()

    second_result = runner.invoke(
        app,
        ["image-publish", "--ref", "ghcr.io/acme/widget:latest"],
    )

    assert second_result.exit_code == 0
    assert not lock_path.exists()
