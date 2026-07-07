"""Concrete `SourceProvider` adapter backed by `git ls-remote`.

Structurally satisfies `odoo_forge.ports.source_provider.SourceProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `git`.
"""

import re
import subprocess

from odoo_forge.manifest.errors import (
    AuthenticationError,
    NetworkError,
    RefNotFoundError,
    ResolutionError,
)

_BARE_SHA = re.compile(r"[0-9a-f]{40}")

_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "permission denied",
    "publickey",
)


class GitSourceProvider:
    """Resolves `url`/`ref` pairs to full commit SHAs via `git ls-remote`."""

    def resolve_ref(self, url: str, ref: str) -> str:
        if _BARE_SHA.fullmatch(ref):
            return ref

        try:
            result = subprocess.run(
                ["git", "ls-remote", url, ref],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ResolutionError(f"git executable not found: {exc}") from exc

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

    raise AssertionError("unreachable: non-empty stdout always yields at least one sha")


__all__ = ["GitSourceProvider"]
