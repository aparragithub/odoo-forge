from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from odoo_forge.manifest.errors import CheckoutError, ScanError
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import ScannedRepo
from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import main
from odoo_forge_cli.main import app

runner = CliRunner()

_MANIFEST_TEXT = (
    "name: onboarding-project\n"
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
    def __init__(
        self,
        *,
        scan_error: bool = False,
        fail_checkout: bool = False,
        stale_checkout: bool = False,
    ) -> None:
        self.checkout_calls: list[tuple[str, str, Path]] = []
        self._scan_error = scan_error
        self._fail_checkout = fail_checkout
        self._stale_checkout = stale_checkout

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        if self._fail_checkout:
            raise CheckoutError(f"cannot reach remote for '{url}'")
        self.checkout_calls.append((url, commit, dest))

    def scan(self, roots: object) -> list[ScannedRepo]:
        if self._scan_error:
            raise ScanError("cannot inspect workspace")
        if not self.checkout_calls:
            if self._stale_checkout:
                return [
                    ScannedRepo(
                        path=main._HOST_ROOTS["community"] / "core" / "odoo",
                        url="https://github.com/odoo/odoo.git",
                        commit="stale-sha",
                    ),
                    ScannedRepo(
                        path=main._HOST_ROOTS["custom"] / "custom-x" / "custom-x",
                        url="https://example.com/custom-x.git",
                        commit="stale-sha",
                    ),
                ]
            return []
        return [
            ScannedRepo(
                path=dest,
                url=url,
                commit="stale-sha" if self._stale_checkout else commit,
            )
            for url, commit, dest in self.checkout_calls
        ]

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def _write_manifest_and_lock(tmp_path: Path, *, generated_from: str | None = None) -> Path:
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(_MANIFEST_TEXT)
    manifest = Manifest.model_validate(yaml.safe_load(_MANIFEST_TEXT))
    lock = Lockfile(
        generated_from=generated_from or compute_manifest_hash(manifest),
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
    (tmp_path / "project.lock").write_text(lock.to_canonical_json())
    return manifest_path


def test_onboard_projects_valid_local_inputs_and_prints_next_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert len(provider.checkout_calls) == 2
    assert "workspace" in result.output.lower()
    assert "next" in result.output.lower()
    assert "runtime" not in result.output.lower()
    assert "database" not in result.output.lower()


def test_onboard_rejects_missing_lock_before_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = tmp_path / "project.yaml"
    manifest.write_text(_MANIFEST_TEXT)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "project.lock" in result.output
    assert not provider.checkout_calls


@pytest.mark.parametrize(
    ("manifest_text", "lock_text"),
    [
        ("name: [malformed", None),
        (_MANIFEST_TEXT, "{malformed-json"),
    ],
)
def test_onboard_rejects_malformed_local_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_text: str,
    lock_text: str | None,
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = tmp_path / "project.yaml"
    manifest.write_text(manifest_text)
    if lock_text is not None:
        (tmp_path / "project.lock").write_text(lock_text)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert not provider.checkout_calls


def test_onboard_rejects_manifest_lock_drift_before_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path, generated_from="stale-manifest-hash")

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "drift" in result.output.lower()
    assert not provider.checkout_calls


def test_onboard_rejects_stale_checkout_evidence_before_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(stale_checkout=True)
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "drift" in result.output.lower() or "stale" in result.output.lower()


def test_onboard_reports_scan_failure_without_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(scan_error=True)
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "cannot inspect workspace" in result.output
    assert not provider.checkout_calls


def test_onboard_reports_checkout_failure_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(fail_checkout=True)
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "cannot reach remote" in result.output
    assert "Traceback" not in result.output
