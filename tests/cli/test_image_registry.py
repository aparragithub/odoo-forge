import pytest
from typer.testing import CliRunner

from odoo_forge.image_registry.errors import (
    RegistryAuthenticationError,
    RegistryImageNotFoundError,
)
from odoo_forge_cli import main
from odoo_forge_cli.main import app

runner = CliRunner()


class _FakeImageRegistryProvider:
    def __init__(
        self,
        *,
        resolved_ref: str = "ghcr.io/acme/widget@sha256:" + "a" * 64,
        validated_ref: str = "ghcr.io/acme/widget@sha256:" + "b" * 64,
        resolve_error: Exception | None = None,
        validate_error: Exception | None = None,
    ) -> None:
        self.resolve_calls: list[str] = []
        self.validate_calls: list[str] = []
        self._resolved_ref = resolved_ref
        self._validated_ref = validated_ref
        self._resolve_error = resolve_error
        self._validate_error = validate_error

    def resolve(self, ref: str) -> str:
        self.resolve_calls.append(ref)
        if self._resolve_error is not None:
            raise self._resolve_error
        return self._resolved_ref

    def validate(self, ref: str) -> str:
        self.validate_calls.append(ref)
        if self._validate_error is not None:
            raise self._validate_error
        return self._validated_ref


def test_image_resolve_prints_canonical_digest_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider(
        resolved_ref="ghcr.io/acme/widget@sha256:" + "c" * 64
    )
    monkeypatch.setattr(main, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, ["image-resolve", "--ref", "ghcr.io/acme/widget:latest"])

    assert result.exit_code == 0
    assert result.output.strip() == "ghcr.io/acme/widget@sha256:" + "c" * 64
    assert fake_provider.resolve_calls == ["ghcr.io/acme/widget:latest"]


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
            "image-validate",
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
        resolve_error=error if command == "image-resolve" else None,
        validate_error=error if command == "image-validate" else None,
    )
    monkeypatch.setattr(main, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, [command, "--ref", ref])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert expected_text in result.output
    assert "Traceback" not in result.output


def test_image_validate_reports_valid_for_existing_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider(
        validated_ref="ghcr.io/acme/widget@sha256:" + "e" * 64
    )
    monkeypatch.setattr(main, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        ["image-validate", "--ref", "ghcr.io/acme/widget@sha256:" + "e" * 64],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "valid: ghcr.io/acme/widget@sha256:" + "e" * 64
    assert fake_provider.validate_calls == ["ghcr.io/acme/widget@sha256:" + "e" * 64]


@pytest.mark.parametrize(
    ("command", "ref"),
    [
        ("image-resolve", "docker.io/acme/widget:latest"),
        ("image-validate", "ghcr.io/acme/widget:not-a-digest"),
    ],
)
def test_image_commands_fail_fast_on_usage_boundary_errors(
    command: str,
    ref: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeImageRegistryProvider()
    monkeypatch.setattr(main, "_make_image_registry_provider", lambda: fake_provider)

    result = runner.invoke(app, [command, "--ref", ref])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert fake_provider.resolve_calls == []
    assert fake_provider.validate_calls == []
