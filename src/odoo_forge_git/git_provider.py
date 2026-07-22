"""Concrete `SourceProvider` adapter backed by `git ls-remote`.

Structurally satisfies `odoo_forge.ports.source_provider.SourceProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `git`.
"""

import os
import re
import subprocess
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from odoo_forge.manifest.errors import (
    AuthenticationError,
    NetworkError,
    RefNotFoundError,
    ResolutionError,
)

_BARE_SHA = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)
_SCP_REMOTE = re.compile(r"[^@/:]+@([^/:]+):(.+)")

_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "permission denied",
    "publickey",
)
_MISSING_REMOTE_REF = re.compile(r"^fatal: couldn't find remote ref(?: .*)?$", re.MULTILINE)

DEFAULT_TIMEOUT_SECONDS = 30


def _non_interactive_env() -> dict[str, str]:
    """Build a subprocess env that never blocks on credential prompts.

    Starts from the current environment and disables interactive git
    prompting so a missing/expired credential fails fast instead of
    hanging. Also pins the locale so stderr text used for error
    classification (see `_AUTH_MARKERS`) stays stable regardless of the
    caller's locale.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


def _safe_url(url: str) -> str:
    """Project a remote without URI or scp-like userinfo for public errors."""
    if "://" not in url:
        scp_remote = _SCP_REMOTE.fullmatch(url)
        if scp_remote is not None:
            return f"{scp_remote.group(1)}:{scp_remote.group(2)}"
        return "<redacted-remote>" if "@" in url else url

    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return "<redacted-remote>"

    if hostname is None:
        return "<redacted-remote>" if "@" in url else url
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        host = f"{host}:{port}"
    if parts.username is None and parts.password is None:
        return url
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


class GitSourceProvider:
    """Resolves `url`/`ref` pairs to full commit SHAs via `git ls-remote`."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def resolve_ref(self, url: str, ref: str, env_overlay: Mapping[str, str] | None = None) -> str:
        """Resolve `ref` against `url`, merging `env_overlay` over the non-interactive env.

        `env_overlay` is applied on top of `_non_interactive_env()` (e.g. a
        short-lived `GIT_ASKPASS` from `GitCredentialInjector`); when `None`
        the resulting env is byte-for-byte identical to today's behavior.
        Overlay values are never logged, never placed in `_safe_url`, and
        never interpolated into any raised error/exception message.
        """
        if _BARE_SHA.fullmatch(ref):
            return ref

        public_url = _safe_url(url)
        env = {**_non_interactive_env(), **(env_overlay or {})}
        deferred_error: ResolutionError | None = None
        try:
            result = subprocess.run(
                ["git", "ls-remote", url, ref],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
                env=env,
            )
        except FileNotFoundError:
            deferred_error = ResolutionError("git executable not found")
        except OSError as exc:
            deferred_error = ResolutionError(f"failed to execute git: {exc}")
        except subprocess.TimeoutExpired:
            deferred_error = NetworkError(
                public_url,
                f"ref '{ref}': timed out after {self._timeout}s",
            )

        if deferred_error is not None:
            raise deferred_error

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if any(marker in stderr.lower() for marker in _AUTH_MARKERS):
                raise AuthenticationError(public_url)
            if _MISSING_REMOTE_REF.search(stderr):
                raise RefNotFoundError(public_url, ref)
            raise NetworkError(
                public_url,
                f"git ls-remote failed with exit code {result.returncode}",
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise RefNotFoundError(public_url, ref)

        return _select_sha(stdout, ref)


def _select_sha(stdout: str, ref: str) -> str:
    branch_sha: str | None = None
    peeled_tag_sha: str | None = None
    lightweight_tag_sha: str | None = None
    first_sha: str | None = None

    for line in stdout.splitlines():
        if not line.strip():
            continue
        sha, _, refname = line.partition("\t")
        if first_sha is None:
            first_sha = sha
        if refname == f"refs/heads/{ref}":
            branch_sha = sha
        elif refname == f"refs/tags/{ref}^{{}}":
            peeled_tag_sha = sha
        elif refname == f"refs/tags/{ref}":
            lightweight_tag_sha = sha

    for candidate in (branch_sha, peeled_tag_sha, lightweight_tag_sha, first_sha):
        if candidate is not None:
            return candidate

    raise RuntimeError(
        f"no SHA candidate found for ref {ref!r} despite non-empty ls-remote output "
        "(unreachable under normal parsing)"
    )


__all__ = ["GitSourceProvider"]
