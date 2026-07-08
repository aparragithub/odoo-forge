from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.manifest.errors import CheckoutError
from odoo_forge.manifest.lockfile import Lockfile, ResolvedLayer, ResolvedRepo
from odoo_forge_cli import main
from odoo_forge_cli.main import app

runner = CliRunner()

_MANIFEST_TEXT = (
    "name: odoo-idp\n"
    "odoo_version: '19.0'\n"
    "edition: community\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "layers:\n"
    "  - type: git\n"
    "    name: custom-x\n"
    "    repos:\n"
    "      - url: https://example.com/custom-x.git\n"
    "        ref: main\n"
    "client:\n"
    "  addons_path: client/addons\n"
)


class _FakeWorkspaceProvider:
    """Records `checkout` calls in order, no I/O."""

    def __init__(self, fail_on_call: int | None = None) -> None:
        self.checkout_calls: list[tuple[str, str, Path]] = []
        self._fail_on_call = fail_on_call

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        call_index = len(self.checkout_calls)
        if self._fail_on_call is not None and call_index == self._fail_on_call:
            raise CheckoutError(f"cannot reach remote for '{url}'")
        self.checkout_calls.append((url, commit, dest))

    def scan(self, roots: object) -> list[object]:
        raise NotImplementedError

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def _write_manifest_and_lock(tmp_path: Path) -> tuple[Path, Path]:
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(_MANIFEST_TEXT)

    lock = Lockfile(
        generated_from="irrelevant-for-projection",
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="core-sha"
                    )
                ],
            ),
            ResolvedLayer(
                name="custom-x",
                repos=[
                    ResolvedRepo(
                        url="https://example.com/custom-x.git", ref="main", commit="custom-sha"
                    )
                ],
            ),
        ],
    )
    lock_path = tmp_path / "project.lock"
    lock_path.write_text(lock.to_canonical_json())
    return project_yaml, lock_path


def test_valid_lock_projects_every_layer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml, _lock_path = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["project", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_provider.checkout_calls) == 2
    urls = [call[0] for call in fake_provider.checkout_calls]
    assert urls == [
        "https://github.com/odoo/odoo.git",
        "https://example.com/custom-x.git",
    ]


def test_mid_plan_checkout_failure_stops_cleanly_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider(fail_on_call=1)
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml, _lock_path = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["project", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    # Step 1 (core) completed; step 2 (custom-x) raised and stopped execution.
    assert len(fake_provider.checkout_calls) == 1


class _CredentialLeakSafeProvider:
    """A `WorkspaceProvider` double that fails on a specific URL and raises
    `CheckoutError` the way `GitWorkspaceProvider` actually does: naming
    `dest` (derived from the URL's basename, credential-free) rather than
    the raw `url` — mirrors the real adapter's never-splat-the-URL contract.
    """

    def __init__(self, fail_url_substring: str) -> None:
        self.checkout_calls: list[tuple[str, str, Path]] = []
        self._fail_url_substring = fail_url_substring

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        self.checkout_calls.append((url, commit, dest))
        if self._fail_url_substring in url:
            raise CheckoutError(f"cannot check out repo at '{dest}'")

    def scan(self, roots: object) -> list[object]:
        raise NotImplementedError

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def test_mid_plan_failure_names_repo_without_leaking_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `CheckoutError` for a credentialed lock URL must still let the CLI
    name the failing repo (spec: "exits non-zero naming the failing repo"),
    without ever surfacing the embedded credential in the error output."""
    fake_provider = _CredentialLeakSafeProvider(fail_url_substring="custom-x")
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(_MANIFEST_TEXT)

    lock = Lockfile(
        generated_from="irrelevant-for-projection",
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="core-sha"
                    )
                ],
            ),
            ResolvedLayer(
                name="custom-x",
                repos=[
                    ResolvedRepo(
                        url="https://user:secret-token@example.com/custom-x.git",
                        ref="main",
                        commit="custom-sha",
                    )
                ],
            ),
        ],
    )
    (tmp_path / "project.lock").write_text(lock.to_canonical_json())

    result = runner.invoke(app, ["project", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert "custom-x" in result.output  # names the failing repo
    assert "secret-token" not in result.output  # never leaks the credential
    assert "Traceback" not in result.output


def test_missing_lock_exits_clean_one_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(_MANIFEST_TEXT)

    result = runner.invoke(app, ["project", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert not fake_provider.checkout_calls
