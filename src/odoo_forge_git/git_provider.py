"""Concrete `SourceProvider` adapter backed by `git ls-remote`.

Structurally satisfies `odoo_forge.ports.source_provider.SourceProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `git`.
"""

import os
import re
import subprocess

from odoo_forge.manifest.errors import (
    AuthenticationError,
    NetworkError,
    RefNotFoundError,
    ResolutionError,
)

_BARE_SHA = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)

_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "permission denied",
    "publickey",
)

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


class GitSourceProvider:
    """Resolves `url`/`ref` pairs to full commit SHAs via `git ls-remote`."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def resolve_ref(self, url: str, ref: str) -> str:
        if _BARE_SHA.fullmatch(ref):
            return ref

        try:
            result = subprocess.run(
                ["git", "ls-remote", url, ref],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
                env=_non_interactive_env(),
            )
        except FileNotFoundError as exc:
            raise ResolutionError(f"git executable not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise NetworkError(
                url,
                f"ref '{ref}': timed out after {self._timeout}s",
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if any(marker in stderr.lower() for marker in _AUTH_MARKERS):
                raise AuthenticationError(url)
            raise NetworkError(url, stderr)

        stdout = result.stdout.strip()
        if not stdout:
            raise RefNotFoundError(url, ref)

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
