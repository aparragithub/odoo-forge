"""Shared askpass-based credential injection for the git-backed adapters.

Both `GitSourceProvider.resolve_ref` and `GitWorkspaceProvider.checkout` need
an identical, process-scoped way to hand a resolved credential to `git`
without ever placing it in a URL, argv, log line, or exception message.

`GitCredentialInjector.askpass_env` resolves the secret once, writes a
short-lived `GIT_ASKPASS` helper script to a `0700` temp file, yields an env
overlay pointing `GIT_ASKPASS` at that script, and unlinks it in a `finally`
block regardless of how the wrapped block exits. This mirrors
`SopsEnvFileInjector.env_file`'s `0600`-tmp-file/`finally` lifecycle.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from odoo_forge.credentials.errors import CredentialError, CredentialUnavailableError
from odoo_forge.credentials.types import CredentialHandle, CredentialInjectionDescriptor

CredentialResolver = Callable[[CredentialHandle], str]

_ASKPASS_SCRIPT_TEMPLATE = """\
#!/usr/bin/env python3
import sys

sys.stdout.write({secret!r})
sys.stdout.write("\\n")
"""


class GitCredentialInjector:
    """Resolve a credential only while a single `git` subprocess needs it."""

    @contextmanager
    def askpass_env(
        self,
        descriptor: CredentialInjectionDescriptor,
        resolver: CredentialResolver,
    ) -> Iterator[dict[str, str]]:
        """Yield an env overlay with `GIT_ASKPASS` set to a single-use script.

        The script is created with mode `0700`, prints the resolved secret on
        stdout when invoked by git's askpass protocol, and is unlinked in a
        `finally` block so it never outlives this context manager, whether
        the wrapped block succeeds, raises, or times out.
        """
        value = self._resolve(descriptor.handle, resolver)
        fd, raw_path = tempfile.mkstemp(prefix="odoo-forge-askpass-", suffix=".py")
        path = Path(raw_path)
        try:
            os.fchmod(fd, 0o700)
            with os.fdopen(fd, "w", encoding="utf-8") as script_file:
                script_file.write(_ASKPASS_SCRIPT_TEMPLATE.format(secret=value))
            yield {
                "GIT_ASKPASS": str(path),
                "GIT_TERMINAL_PROMPT": "0",
            }
        finally:
            path.unlink(missing_ok=True)

    def _resolve(self, handle: CredentialHandle, resolver: CredentialResolver) -> str:
        try:
            return resolver(handle)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialUnavailableError() from exc


__all__ = ["CredentialResolver", "GitCredentialInjector"]
