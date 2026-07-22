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
from odoo_forge.manifest.projection import ScannedRepo, build_mount_roots
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

# Mirror the per-manifest HOST table `onboard` builds internally
# (`build_mount_roots(_resolve_mount_base(), parsed)`), so the fake provider's
# scanned paths line up with the roots the command actually resolves. The
# `custom-x` layer defaults to the `custom` category, nesting under
# `custom/default` in the pure mount model.
_HOST_ROOTS = build_mount_roots(
    main._resolve_mount_base(), Manifest.model_validate(yaml.safe_load(_MANIFEST_TEXT))
)


class _FakeWorkspaceProvider:
    def __init__(
        self,
        *,
        scan_error: bool = False,
        fail_checkout: bool = False,
        stale_checkout: bool = False,
        post_checkout_stale: bool = False,
    ) -> None:
        self.checkout_calls: list[tuple[str, str, Path]] = []
        self._scan_error = scan_error
        self._fail_checkout = fail_checkout
        self._stale_checkout = stale_checkout
        self._post_checkout_stale = post_checkout_stale

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
                        path=_HOST_ROOTS["community"] / "core" / "odoo",
                        url="https://github.com/odoo/odoo.git",
                        commit="stale-sha",
                    ),
                    ScannedRepo(
                        path=_HOST_ROOTS["custom/default"] / "custom-x" / "custom-x",
                        url="https://example.com/custom-x.git",
                        commit="stale-sha",
                    ),
                ]
            return []
        return [
            ScannedRepo(
                path=dest,
                url=url,
                commit="stale-sha" if self._stale_checkout or self._post_checkout_stale else commit,
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
    assert not provider.checkout_calls


def test_onboard_reports_post_projection_drift_as_safety_net(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(post_checkout_stale=True)
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "drift" in result.output.lower()
    # Preflight passed and checkout ran; the drift was caught only by the
    # post-projection safety-net re-scan, not by preflight.
    assert provider.checkout_calls
    assert "next" not in result.output.lower()


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


def _write_module(root: Path, name: str, content: str) -> None:
    module_dir = root / name
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "__manifest__.py").write_text(content, encoding="utf-8")


def test_onboard_rejects_missing_module_dependency_after_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`forge onboard` is a valid path to a fully materialized workspace that
    never goes through `forge validate` — it MUST run the same
    module-dependency check once the workspace is confirmed materialized, not
    leave it to an optional later `forge validate` call."""
    base = tmp_path / "mount-base"
    monkeypatch.setattr(main, "_resolve_mount_base", lambda: base)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    _write_module(base / "community", "mod_a", "{'name': 'Mod A', 'depends': ['mod_missing']}")

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "mod_a" in result.output
    assert "mod_missing" in result.output
    # The workspace WAS fully materialized (checkout ran) before the
    # dependency check rejected it — this proves the check runs against the
    # real, projected addons_path, not before materialization.
    assert provider.checkout_calls
    assert "next" not in result.output.lower()


def test_onboard_succeeds_when_module_dependencies_are_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "mount-base"
    monkeypatch.setattr(main, "_resolve_mount_base", lambda: base)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    _write_module(base / "community", "mod_b", "{'name': 'Mod B'}")
    _write_module(base / "community", "mod_a", "{'name': 'Mod A', 'depends': ['mod_b']}")

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "next" in result.output.lower()


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
