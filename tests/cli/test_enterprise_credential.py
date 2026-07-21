"""Composition-root fail-fast wiring: `lock`/`onboard` resolve the
conventional Enterprise source credential before any git fetch.

Highest-risk slice of `source-credentials-model`: a fake resolver stands in
for the real SOPS+age pipeline throughout — never real `sops`/`age`. Leak
discipline is asserted explicitly: the resolved secret marker must never
appear in CLI output.
"""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from odoo_forge.credentials.conventions import ENTERPRISE_SOURCE_CREDENTIAL_HANDLE
from odoo_forge.credentials.errors import CredentialUnavailableError
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.manifest.errors import CheckoutError
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
from odoo_forge_git.git_credential_injector import CredentialResolver

runner = CliRunner()

_SECRET_MARKER = "s3cr3t-enterprise-token-marker"

_ENTERPRISE_MANIFEST_TEXT = (
    "name: enterprise-project\n"
    "odoo_version: '19.0'\n"
    "edition: enterprise\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "client:\n"
    "  addons_path: client/addons\n"
)

_COMMUNITY_MANIFEST_TEXT = (
    "name: community-project\n"
    "odoo_version: '19.0'\n"
    "edition: community\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "client:\n"
    "  addons_path: client/addons\n"
)

_ENTERPRISE_URL = "https://github.com/odoo/enterprise.git"


class _FakeSourceProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def resolve_ref(self, url: str, ref: str, env_overlay: dict[str, str] | None = None) -> str:
        self.calls.append((url, ref, env_overlay))
        return f"sha-{ref}"


class _FakeWorkspaceProvider:
    def __init__(self) -> None:
        self.checkout_calls: list[tuple[str, str, Path, dict[str, str] | None]] = []
        self.scan_results: list[ScannedRepo] = []

    def checkout(
        self, url: str, commit: str, dest: Path, env_overlay: dict[str, str] | None = None
    ) -> None:
        self.checkout_calls.append((url, commit, dest, env_overlay))
        self.scan_results.append(ScannedRepo(path=dest, url=url, commit=commit))

    def scan(self, roots: object) -> list[ScannedRepo]:
        return list(self.scan_results)

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def _succeeding_resolver_calls() -> tuple[list[CredentialHandle], CredentialResolver]:
    calls: list[CredentialHandle] = []

    def resolver(handle: CredentialHandle) -> str:
        calls.append(handle)
        return _SECRET_MARKER

    return calls, resolver


def _raising_resolver() -> CredentialResolver:
    def resolver(handle: CredentialHandle) -> str:
        raise CredentialUnavailableError()

    return resolver


def _write_manifest(tmp_path: Path, text: str) -> Path:
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(text)
    return manifest_path


def _write_onboard_lock(tmp_path: Path, manifest_text: str) -> Path:
    manifest_path = _write_manifest(tmp_path, manifest_text)
    manifest = Manifest.model_validate(yaml.safe_load(manifest_text))
    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="core-sha"
                    )
                ],
            ),
        ],
    )
    (tmp_path / "project.lock").write_text(lock.to_canonical_json())
    return manifest_path


# ---------------------------------------------------------------------------
# Fail-fast: missing/unavailable conventional credential (both commands)
# ---------------------------------------------------------------------------


def test_lock_fails_fast_when_enterprise_credential_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeSourceProvider()
    monkeypatch.setattr(main, "_make_provider", lambda: fake_provider)
    monkeypatch.setattr(
        main, "_make_enterprise_credential_resolver", lambda **kwargs: _raising_resolver()
    )
    manifest_path = _write_manifest(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert "Enterprise credential required but unavailable" in result.output
    assert "Traceback" not in result.output
    assert not fake_provider.calls
    assert not (tmp_path / "project.lock").exists()


def test_onboard_fails_fast_when_enterprise_credential_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)
    monkeypatch.setattr(
        main, "_make_enterprise_credential_resolver", lambda **kwargs: _raising_resolver()
    )
    manifest_path = _write_onboard_lock(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert "Enterprise credential required but unavailable" in result.output
    assert "Traceback" not in result.output
    assert not fake_provider.checkout_calls


def test_lock_and_onboard_fail_identically_on_missing_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both commands hit the same error class/message shape regardless of
    which concrete git adapter (`GitSourceProvider`/`GitWorkspaceProvider`)
    would otherwise have performed the fetch."""
    monkeypatch.setattr(main, "_make_provider", lambda: _FakeSourceProvider())
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: _FakeWorkspaceProvider())
    monkeypatch.setattr(
        main, "_make_enterprise_credential_resolver", lambda **kwargs: _raising_resolver()
    )

    (tmp_path / "lock-case").mkdir()
    (tmp_path / "onboard-case").mkdir()
    lock_manifest = _write_manifest(tmp_path / "lock-case", _ENTERPRISE_MANIFEST_TEXT)
    onboard_manifest = _write_onboard_lock(tmp_path / "onboard-case", _ENTERPRISE_MANIFEST_TEXT)

    lock_result = runner.invoke(app, ["lock", "--manifest", str(lock_manifest)])
    onboard_result = runner.invoke(app, ["onboard", "--manifest", str(onboard_manifest)])

    def _error_line(output: str) -> str:
        return next(line for line in output.splitlines() if line.startswith("error:"))

    assert lock_result.exit_code == 1
    assert onboard_result.exit_code == 1
    assert _error_line(lock_result.output) == _error_line(onboard_result.output)


# ---------------------------------------------------------------------------
# Happy path: conventional credential resolves and threads into the adapter
# ---------------------------------------------------------------------------


def test_lock_resolves_and_threads_credential_into_enterprise_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    monkeypatch.setattr(main, "_make_provider", lambda: fake_provider)
    monkeypatch.setattr(main, "_make_enterprise_credential_resolver", lambda **kwargs: resolver)
    manifest_path = _write_manifest(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    # The preflight check resolves the conventional handle exactly once
    # before `build_lock` runs. `build_lock` itself never emits a
    # `resolve_ref` call for the Enterprise URL yet (external prerequisite,
    # out of this change's scope — see `test_bind_enterprise_source_provider_
    # threads_overlay_before_fetch` for the direct proof that the bound
    # provider WOULD thread `env_overlay` into that call once it exists);
    # the `core` layer call it does make is untouched (no overlay).
    assert calls == [ENTERPRISE_SOURCE_CREDENTIAL_HANDLE]
    assert fake_provider.calls == [("https://github.com/odoo/odoo.git", "19.0", None)]


def test_lock_skips_credential_resolution_for_non_enterprise_edition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    monkeypatch.setattr(main, "_make_provider", lambda: fake_provider)
    monkeypatch.setattr(main, "_make_enterprise_credential_resolver", lambda **kwargs: resolver)
    manifest_path = _write_manifest(tmp_path, _COMMUNITY_MANIFEST_TEXT)

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    assert calls == []
    assert all(env_overlay is None for _url, _ref, env_overlay in fake_provider.calls)


def test_onboard_skips_credential_resolution_for_non_enterprise_edition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    calls, resolver = _succeeding_resolver_calls()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)
    monkeypatch.setattr(main, "_make_enterprise_credential_resolver", lambda **kwargs: resolver)
    manifest_path = _write_onboard_lock(tmp_path, _COMMUNITY_MANIFEST_TEXT)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    assert calls == []


# ---------------------------------------------------------------------------
# Direct wrapper unit tests: the actual env_overlay threading, exercised
# without depending on `build_lock`/`project_workspace` resolving the
# Enterprise layer end-to-end (external prerequisite, out of this change's
# scope — see design's "External Prerequisite Dependency").
# ---------------------------------------------------------------------------


def test_bind_enterprise_source_provider_threads_overlay_before_fetch() -> None:
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_ENTERPRISE_MANIFEST_TEXT))

    bound = main._bind_enterprise_source_provider(manifest, fake_provider, resolver)
    sha = bound.resolve_ref(_ENTERPRISE_URL, "19.0")

    assert sha == "sha-19.0"
    assert calls == [ENTERPRISE_SOURCE_CREDENTIAL_HANDLE]
    assert len(fake_provider.calls) == 1
    url, ref, env_overlay = fake_provider.calls[0]
    assert (url, ref) == (_ENTERPRISE_URL, "19.0")
    assert env_overlay is not None
    assert env_overlay["GIT_ASKPASS"]
    assert env_overlay["GIT_TERMINAL_PROMPT"] == "0"


def test_bind_enterprise_source_provider_passes_through_other_urls_untouched() -> None:
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_ENTERPRISE_MANIFEST_TEXT))

    bound = main._bind_enterprise_source_provider(manifest, fake_provider, resolver)
    bound.resolve_ref("https://github.com/odoo/odoo.git", "19.0")

    assert calls == []
    url, _ref, env_overlay = fake_provider.calls[0]
    assert url == "https://github.com/odoo/odoo.git"
    assert env_overlay is None


def test_bind_enterprise_source_provider_fails_fast_before_any_fetch() -> None:
    fake_provider = _FakeSourceProvider()
    manifest = Manifest.model_validate(yaml.safe_load(_ENTERPRISE_MANIFEST_TEXT))

    bound = main._bind_enterprise_source_provider(manifest, fake_provider, _raising_resolver())

    with pytest.raises(CredentialUnavailableError):
        bound.resolve_ref(_ENTERPRISE_URL, "19.0")
    assert not fake_provider.calls


def test_bind_enterprise_source_provider_is_a_no_op_for_community_edition() -> None:
    fake_provider = _FakeSourceProvider()
    _calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_COMMUNITY_MANIFEST_TEXT))

    bound = main._bind_enterprise_source_provider(manifest, fake_provider, resolver)

    assert bound is fake_provider


def test_bind_enterprise_workspace_provider_threads_overlay_before_checkout() -> None:
    fake_provider = _FakeWorkspaceProvider()
    calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_ENTERPRISE_MANIFEST_TEXT))

    bound = main._bind_enterprise_workspace_provider(manifest, fake_provider, resolver)
    bound.checkout(_ENTERPRISE_URL, "deadbeef", Path("/mnt/enterprise/core/enterprise"))

    assert calls == [ENTERPRISE_SOURCE_CREDENTIAL_HANDLE]
    url, commit, _dest, env_overlay = fake_provider.checkout_calls[0]
    assert (url, commit) == (_ENTERPRISE_URL, "deadbeef")
    assert env_overlay is not None
    assert env_overlay["GIT_ASKPASS"]


def test_bind_enterprise_workspace_provider_fails_fast_before_any_checkout() -> None:
    fake_provider = _FakeWorkspaceProvider()
    manifest = Manifest.model_validate(yaml.safe_load(_ENTERPRISE_MANIFEST_TEXT))

    bound = main._bind_enterprise_workspace_provider(manifest, fake_provider, _raising_resolver())

    with pytest.raises(CredentialUnavailableError):
        bound.checkout(_ENTERPRISE_URL, "deadbeef", Path("/mnt/enterprise/core/enterprise"))
    assert not fake_provider.checkout_calls


def test_bind_enterprise_workspace_provider_scan_and_promote_pass_through() -> None:
    fake_provider = _FakeWorkspaceProvider()
    _calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_ENTERPRISE_MANIFEST_TEXT))

    bound = main._bind_enterprise_workspace_provider(manifest, fake_provider, resolver)

    assert bound.scan([]) == []
    with pytest.raises(NotImplementedError):
        bound.promote(Path("/a"), Path("/b"), "branch")


# ---------------------------------------------------------------------------
# Leak discipline: the resolved secret never appears in output/errors
# ---------------------------------------------------------------------------


def test_secret_never_leaks_into_lock_output_on_checkout_style_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when the underlying adapter call fails after a successful
    credential resolution, the resolved secret must never appear in the
    CLI's rendered error output."""

    class _FailingAfterCredentialSourceProvider:
        def resolve_ref(self, url: str, ref: str, env_overlay: dict[str, str] | None = None) -> str:
            if url == _ENTERPRISE_URL:
                raise CheckoutError(f"cannot reach remote for '{url}'")
            return f"sha-{ref}"

    calls, resolver = _succeeding_resolver_calls()
    monkeypatch.setattr(main, "_make_provider", lambda: _FailingAfterCredentialSourceProvider())
    monkeypatch.setattr(main, "_make_enterprise_credential_resolver", lambda **kwargs: resolver)
    manifest_path = _write_manifest(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert _SECRET_MARKER not in result.output
    assert "Traceback" not in result.output
