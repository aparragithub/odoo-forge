"""Composition-root logic for the conventional Enterprise source credential.

Extracted out of `odoo_forge_cli.main` (which stays a thin Typer presentation
layer): builds the resolver, threads it through `lock`/`onboard`'s fail-fast
preflight check, and wraps the git-backed `SourceProvider`/`WorkspaceProvider`
adapters so the injected `GIT_ASKPASS` env only ever reaches the fixed
Enterprise source URL — never any other URL those adapters might resolve.

Security note (host allow-list): `manifest.enterprise.url` is a
user-controlled string (it can be overridden in `project.yaml`). Before
handing the resolved credential to `git` via askpass, the wrapper functions
below verify the URL's HOST is in a fixed allow-list — by default, only the
host of the official Enterprise source. This prevents a malicious/typo'd
manifest from exfiltrating the credential to an arbitrary remote.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from odoo_forge.credentials.conventions import (
    ENTERPRISE_SOURCE_CREDENTIAL_HANDLE,
    ENTERPRISE_SOURCE_TARGET,
)
from odoo_forge.credentials.materialization import materialize_for_target
from odoo_forge.credentials.types import CredentialHandle, CredentialResolver
from odoo_forge.manifest.errors import ManifestInputError
from odoo_forge.manifest.projection import ScannedRepo
from odoo_forge.manifest.schema import Manifest
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge_docker.credential_injection import SopsCommandResolver
from odoo_forge_git.git_credential_injector import GitCredentialInjector

# The only host the conventional Enterprise credential may ever be injected
# against. Derived from the official (and, today, only) Enterprise source
# URL. No user-facing configuration surface exists for this yet — that is a
# deliberate follow-up, out of scope here.
_DEFAULT_ENTERPRISE_URL = "https://github.com/odoo/enterprise.git"
_ALLOWED_ENTERPRISE_CREDENTIAL_HOSTS = frozenset(
    host for host in (urlsplit(_DEFAULT_ENTERPRISE_URL).hostname,) if host
)


def _extract_host(url: str) -> str | None:
    """Return `url`'s lowercased host, or `None` if it cannot be parsed.

    Handles the scp-like shorthand (`git@github.com:odoo/enterprise.git`) by
    rewriting it into a parseable `ssh://` form first. Uses
    `urlsplit(...).hostname`, which already strips any userinfo
    (`user@host`) and lowercases the result, so lookalike hosts
    (`github.com.attacker.com`) and userinfo tricks
    (`github.com@attacker.com`) never match the allow-list by accident.
    """
    candidate = url
    if "://" not in candidate and "@" in candidate and ":" in candidate:
        userinfo_and_host, _sep, path = candidate.partition(":")
        candidate = f"ssh://{userinfo_and_host}/{path}"
    return urlsplit(candidate).hostname


def _assert_allowed_enterprise_host(url: str) -> None:
    """Fail fast, before any credential is resolved, unless `url`'s host is
    EXACTLY one of `_ALLOWED_ENTERPRISE_CREDENTIAL_HOSTS` — never a
    substring/`endswith` match. An unparseable `url` is rejected, never
    treated as allowed.
    """
    host = _extract_host(url)
    if host is None or host not in _ALLOWED_ENTERPRISE_CREDENTIAL_HOSTS:
        raise ManifestInputError(
            f"Enterprise credential injection refused: host '{host}' is not "
            "an allowed enterprise credential host"
        )


class _MemoizingCredentialResolver:
    """Wrap a `CredentialResolver`, calling the underlying resolver at most
    once and replaying the cached value afterward.

    Collapses the double resolution that used to happen once per
    `lock`/`onboard` invocation (the fail-fast preflight check, then again at
    actual fetch/checkout time) into a single materialization — `sops
    --decrypt` runs once, halving the plaintext-secret exposure window.
    Fail-fast semantics are preserved: if the underlying resolver raises, the
    exception propagates and nothing is cached, so a retried call still
    fails.
    """

    def __init__(self, resolver: CredentialResolver) -> None:
        self._resolver = resolver
        self._cached: str | None = None

    def __call__(self, handle: CredentialHandle) -> str:
        if self._cached is None:
            self._cached = self._resolver(handle)
        return self._cached


def _make_enterprise_credential_resolver(
    *, credentials_file: Path = Path("credentials.sops.yaml")
) -> CredentialResolver:
    """Composition root: the ONE place the Enterprise source credential
    resolver is built — reuses `SopsCommandResolver`, the same handle ->
    plaintext resolver already used for Docker/backend secrets, since both
    resolve opaque handles from the same `credentials.sops.yaml` document.

    The returned resolver memoizes its result (see
    `_MemoizingCredentialResolver`) so callers sharing this single instance
    (preflight check + actual fetch) only trigger one real `sops --decrypt`
    invocation per `lock`/`onboard` run.
    """
    return _MemoizingCredentialResolver(SopsCommandResolver(credentials_file))


def _preflight_enterprise_source_credential(
    manifest: Manifest, resolver: CredentialResolver
) -> None:
    """Fail fast, before any git fetch, when `manifest.edition == 'enterprise'`.

    Resolves the conventional Enterprise source credential
    (`ENTERPRISE_SOURCE_CREDENTIAL_HANDLE`/`ENTERPRISE_SOURCE_TARGET`)
    through the exact same askpass lifecycle a real fetch would use
    (`materialize_for_target` + `GitCredentialInjector.askpass_env`), then
    immediately discards the resulting env overlay — this call's only
    purpose is to surface `CredentialUnavailableError`/
    `CredentialTargetRejectedError` (both subclasses of `CredentialError`)
    before `lock`/`onboard` do anything else, identically whether the
    underlying adapter would have been `GitSourceProvider` or
    `GitWorkspaceProvider`. A no-op for every non-enterprise edition; never
    attempts an unauthenticated fetch first.

    When `resolver` is the memoizing resolver `_make_enterprise_credential_
    resolver` returns, this call is what triggers the ONE real resolution;
    the later real fetch/checkout (via `_bind_enterprise_source_provider`/
    `_bind_enterprise_workspace_provider`) replays the cached value.
    """
    if manifest.edition != "enterprise":
        return
    descriptor = materialize_for_target(
        ENTERPRISE_SOURCE_CREDENTIAL_HANDLE, ENTERPRISE_SOURCE_TARGET
    )
    with GitCredentialInjector().askpass_env(descriptor, resolver):
        pass


class _EnterpriseCredentialSourceProvider:
    """Wrap a `SourceProvider`, threading the conventional Enterprise source
    credential's askpass env into `resolve_ref` only when `url` matches the
    manifest's Enterprise source URL. Every other URL passes through
    untouched — no credential concern for community/custom layers.

    Fail-fast: the credential is resolved BEFORE the wrapped `resolve_ref`
    call, so a missing SOPS entry or an unusable age key aborts before any
    fetch attempt for that URL — never an unauthenticated fetch first.
    """

    def __init__(
        self, inner: SourceProvider, enterprise_url: str, resolver: CredentialResolver
    ) -> None:
        self._inner = inner
        self._enterprise_url = enterprise_url
        self._resolver = resolver
        self._injector = GitCredentialInjector()

    def resolve_ref(self, url: str, ref: str) -> str:
        if url != self._enterprise_url:
            return self._inner.resolve_ref(url, ref)

        descriptor = materialize_for_target(
            ENTERPRISE_SOURCE_CREDENTIAL_HANDLE, ENTERPRISE_SOURCE_TARGET
        )
        with self._injector.askpass_env(descriptor, self._resolver) as env_overlay:
            # `SourceProvider` is a structural Protocol that never declares
            # `env_overlay`; only the concrete git adapter this composition
            # root actually wires accepts it. See `git_provider.GitSourceProvider.resolve_ref`.
            return self._inner.resolve_ref(  # type: ignore[call-arg]
                url, ref, env_overlay=env_overlay
            )


class _EnterpriseCredentialWorkspaceProvider:
    """Wrap a `WorkspaceProvider`, threading the conventional Enterprise
    source credential's askpass env into `checkout` only when `url` matches
    the manifest's Enterprise source URL. `scan`/`promote` pass through
    unchanged — no credential concern there. Same fail-fast contract as
    `_EnterpriseCredentialSourceProvider`.
    """

    def __init__(
        self, inner: WorkspaceProvider, enterprise_url: str, resolver: CredentialResolver
    ) -> None:
        self._inner = inner
        self._enterprise_url = enterprise_url
        self._resolver = resolver
        self._injector = GitCredentialInjector()

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        if url != self._enterprise_url:
            self._inner.checkout(url, commit, dest)
            return

        descriptor = materialize_for_target(
            ENTERPRISE_SOURCE_CREDENTIAL_HANDLE, ENTERPRISE_SOURCE_TARGET
        )
        with self._injector.askpass_env(descriptor, self._resolver) as env_overlay:
            # See the matching note in `_EnterpriseCredentialSourceProvider.resolve_ref`.
            self._inner.checkout(  # type: ignore[call-arg]
                url, commit, dest, env_overlay=env_overlay
            )

    def scan(self, roots: Sequence[Path]) -> list[ScannedRepo]:
        return self._inner.scan(roots)

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        self._inner.promote(source, dest, branch)


def _bind_enterprise_source_provider(
    manifest: Manifest, provider: SourceProvider, resolver: CredentialResolver
) -> SourceProvider:
    """Bind `provider` to the conventional Enterprise credential when (and
    only when) `manifest.edition == 'enterprise'`. Identical wiring is used
    whether `provider` is a `GitSourceProvider` (`lock`'s `ls-remote`
    resolution) or wraps one — see `_bind_enterprise_workspace_provider` for
    the `onboard`/`checkout` counterpart.

    Fails fast (`ManifestInputError`) if `manifest.enterprise.url`'s host is
    not allow-listed, BEFORE building the wrapper or resolving any
    credential — see the module docstring's security note.
    """
    if manifest.edition != "enterprise":
        return provider
    assert manifest.enterprise is not None  # guaranteed by `Manifest._validate_enterprise_block`
    _assert_allowed_enterprise_host(manifest.enterprise.url)
    return _EnterpriseCredentialSourceProvider(provider, manifest.enterprise.url, resolver)


def _bind_enterprise_workspace_provider(
    manifest: Manifest, provider: WorkspaceProvider, resolver: CredentialResolver
) -> WorkspaceProvider:
    """Bind `provider` to the conventional Enterprise credential when (and
    only when) `manifest.edition == 'enterprise'`. See
    `_bind_enterprise_source_provider` for the `lock`/`resolve_ref`
    counterpart, including the host allow-list fail-fast contract.
    """
    if manifest.edition != "enterprise":
        return provider
    assert manifest.enterprise is not None  # guaranteed by `Manifest._validate_enterprise_block`
    _assert_allowed_enterprise_host(manifest.enterprise.url)
    return _EnterpriseCredentialWorkspaceProvider(provider, manifest.enterprise.url, resolver)


__all__ = [
    "_ALLOWED_ENTERPRISE_CREDENTIAL_HOSTS",
    "_MemoizingCredentialResolver",
    "_bind_enterprise_source_provider",
    "_bind_enterprise_workspace_provider",
    "_make_enterprise_credential_resolver",
    "_preflight_enterprise_source_credential",
]
