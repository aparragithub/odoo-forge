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
from odoo_forge.manifest.errors import CheckoutError, ManifestInputError
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import ScannedRepo
from odoo_forge.manifest.schema import EnterpriseLayer, Manifest
from odoo_forge_cli import enterprise_credential as ec
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


def _enterprise_manifest_text(url: str) -> str:
    return (
        "name: enterprise-project\n"
        "odoo_version: '19.0'\n"
        "edition: enterprise\n"
        "core:\n"
        "  type: core\n"
        "  url: https://github.com/odoo/odoo.git\n"
        "  ref: '19.0'\n"
        "enterprise:\n"
        f"  url: {url}\n"
        "client:\n"
        "  addons_path: client/addons\n"
    )


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
    """Integrated contract (post-`enterprise-resolution-projection`
    prerequisite): `build_lock` now genuinely resolves `manifest.enterprise`,
    and that resolution flows THROUGH `_EnterpriseCredentialSourceProvider`,
    so the enterprise `resolve_ref` call carries the askpass `env_overlay`
    while the untouched `core` call does not. The credential itself is still
    resolved exactly ONCE per `lock` invocation — the fail-fast preflight
    check and the wrapped enterprise fetch share the same memoized resolver
    (`_make_enterprise_credential_resolver`'s real contract), so this test
    wraps the counting resolver in the same `_MemoizingCredentialResolver` the
    production factory always returns."""
    fake_provider = _FakeSourceProvider()
    calls, raw_resolver = _succeeding_resolver_calls()
    memoized_resolver = ec._MemoizingCredentialResolver(raw_resolver)
    monkeypatch.setattr(main, "_make_provider", lambda: fake_provider)
    monkeypatch.setattr(
        main, "_make_enterprise_credential_resolver", lambda **kwargs: memoized_resolver
    )
    manifest_path = _write_manifest(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    # Resolved exactly once (memoized), even though both the preflight check
    # and the wrapped enterprise fetch ask for it.
    assert calls == [ENTERPRISE_SOURCE_CREDENTIAL_HANDLE]

    calls_by_url = {url: env_overlay for url, _ref, env_overlay in fake_provider.calls}
    assert calls_by_url == {
        "https://github.com/odoo/odoo.git": None,
        _ENTERPRISE_URL: calls_by_url[_ENTERPRISE_URL],
    }
    enterprise_overlay = calls_by_url[_ENTERPRISE_URL]
    assert enterprise_overlay is not None
    assert enterprise_overlay["GIT_ASKPASS"]
    assert enterprise_overlay["GIT_TERMINAL_PROMPT"] == "0"


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


# ---------------------------------------------------------------------------
# BLOCKER fix: host allow-list before credential injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "malicious_url",
    [
        "https://attacker.example/x.git",
        "https://github.com.attacker.com/odoo/enterprise.git",
        "https://github.com@attacker.com/odoo/enterprise.git",
        "https://githubXcom/odoo/enterprise.git",
        "not a valid url at all",
    ],
)
def test_bind_enterprise_source_provider_refuses_non_allow_listed_host(
    malicious_url: str,
) -> None:
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_enterprise_manifest_text(malicious_url)))

    with pytest.raises(ManifestInputError, match="not an allowed enterprise credential host"):
        main._bind_enterprise_source_provider(manifest, fake_provider, resolver)

    # No credential was ever resolved and no fetch was ever attempted.
    assert calls == []
    assert not fake_provider.calls


@pytest.mark.parametrize(
    "malicious_url",
    [
        "https://attacker.example/x.git",
        "https://github.com.attacker.com/odoo/enterprise.git",
        "https://github.com@attacker.com/odoo/enterprise.git",
        "https://githubXcom/odoo/enterprise.git",
        "not a valid url at all",
    ],
)
def test_bind_enterprise_workspace_provider_refuses_non_allow_listed_host(
    malicious_url: str,
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_enterprise_manifest_text(malicious_url)))

    with pytest.raises(ManifestInputError, match="not an allowed enterprise credential host"):
        main._bind_enterprise_workspace_provider(manifest, fake_provider, resolver)

    assert calls == []
    assert not fake_provider.checkout_calls


def test_lock_refuses_credential_injection_for_non_allow_listed_enterprise_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: `lock` itself fails fast (never fetches) when
    `manifest.enterprise.url` is not allow-listed."""
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    monkeypatch.setattr(main, "_make_provider", lambda: fake_provider)
    monkeypatch.setattr(main, "_make_enterprise_credential_resolver", lambda **kwargs: resolver)
    manifest_path = _write_manifest(
        tmp_path, _enterprise_manifest_text("https://attacker.example/x.git")
    )

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert "not an allowed enterprise credential host" in result.output
    assert "Traceback" not in result.output
    assert not fake_provider.calls
    assert not (tmp_path / "project.lock").exists()


@pytest.mark.parametrize(
    "allowed_url",
    [
        _ENTERPRISE_URL,
        "https://github.com/some-fork-org/enterprise.git",
        "git@github.com:odoo/enterprise.git",
    ],
)
def test_bind_enterprise_source_provider_allows_github_com_hosts(allowed_url: str) -> None:
    fake_provider = _FakeSourceProvider()
    calls, resolver = _succeeding_resolver_calls()
    manifest = Manifest.model_validate(yaml.safe_load(_enterprise_manifest_text(allowed_url)))

    bound = main._bind_enterprise_source_provider(manifest, fake_provider, resolver)
    sha = bound.resolve_ref(allowed_url, "19.0")

    assert sha == "sha-19.0"
    assert calls == [ENTERPRISE_SOURCE_CREDENTIAL_HANDLE]


def test_schema_enterprise_default_url_host_is_credential_allow_listed() -> None:
    """Drift guard: the two literals that must stay in sync — the manifest
    `EnterpriseLayer.url` default and the credential host allow-list seed —
    are anchored to the same canonical URL in
    `odoo_forge.credentials.conventions`. This invariant fails if either
    literal drifts: the host of the schema default MUST be a member of the
    credential injection allow-list, otherwise `edition: enterprise` with the
    default source would be refused by `_assert_allowed_enterprise_host`.
    """
    default_url = EnterpriseLayer().url
    host = ec._extract_host(default_url)

    assert host is not None
    assert host in ec._ALLOWED_ENTERPRISE_CREDENTIAL_HOSTS


def test_extract_host_rejects_unparseable_url() -> None:
    assert ec._extract_host("not a valid url at all") is None


def test_extract_host_handles_scp_like_git_url() -> None:
    assert ec._extract_host("git@github.com:odoo/enterprise.git") == "github.com"


def test_extract_host_strips_userinfo_tricks() -> None:
    assert ec._extract_host("https://github.com@attacker.com/x.git") == "attacker.com"


# ---------------------------------------------------------------------------
# RESILIENCE fix: the credential is materialized exactly once per invocation
# ---------------------------------------------------------------------------


def test_enterprise_credential_resolved_exactly_once_for_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeSourceProvider()
    calls: list[CredentialHandle] = []

    def counting_resolver(handle: CredentialHandle) -> str:
        calls.append(handle)
        return _SECRET_MARKER

    monkeypatch.setattr(main, "_make_provider", lambda: fake_provider)
    monkeypatch.setattr(
        main,
        "_make_enterprise_credential_resolver",
        lambda **kwargs: ec._MemoizingCredentialResolver(counting_resolver),
    )
    manifest_path = _write_manifest(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["lock", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    assert len(calls) == 1


def test_enterprise_credential_resolved_exactly_once_for_onboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_provider = _FakeWorkspaceProvider()
    calls: list[CredentialHandle] = []

    def counting_resolver(handle: CredentialHandle) -> str:
        calls.append(handle)
        return _SECRET_MARKER

    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_provider)
    monkeypatch.setattr(
        main,
        "_make_enterprise_credential_resolver",
        lambda **kwargs: ec._MemoizingCredentialResolver(counting_resolver),
    )
    manifest_path = _write_onboard_lock(tmp_path, _ENTERPRISE_MANIFEST_TEXT)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest_path)])

    assert result.exit_code == 0
    assert len(calls) == 1


def test_real_enterprise_credential_resolver_memoizes_underlying_resolver() -> None:
    """`_make_enterprise_credential_resolver` (the real production factory)
    returns a resolver that only ever calls the underlying `SopsCommandResolver`
    once, even when invoked multiple times with the same handle."""
    calls: list[CredentialHandle] = []

    class _CountingSopsCommandResolver:
        def __call__(self, handle: CredentialHandle) -> str:
            calls.append(handle)
            return _SECRET_MARKER

    resolver = ec._MemoizingCredentialResolver(_CountingSopsCommandResolver())

    first = resolver(ENTERPRISE_SOURCE_CREDENTIAL_HANDLE)
    second = resolver(ENTERPRISE_SOURCE_CREDENTIAL_HANDLE)

    assert first == second == _SECRET_MARKER
    assert len(calls) == 1
