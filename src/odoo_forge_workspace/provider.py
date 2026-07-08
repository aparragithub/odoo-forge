"""Concrete `WorkspaceProvider` adapter backed by `git clone`/`checkout`.

Structurally satisfies `odoo_forge.ports.workspace_provider.WorkspaceProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `git` for workspace
projection.

Only `checkout` is implemented in this slice (PR-2a). `scan` and `promote`
are scaffolded to raise `NotImplementedError` until PR-2b completes the
adapter's remaining two port methods.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from odoo_forge.manifest.errors import CheckoutError
from odoo_forge.manifest.projection import ScannedRepo

DEFAULT_TIMEOUT_SECONDS = 60


def _non_interactive_env() -> dict[str, str]:
    """Build a subprocess env that never blocks on credential prompts.

    Mirrors `odoo_forge_git.git_provider._non_interactive_env`.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


class GitWorkspaceProvider:
    """Checks out `url`/`commit` pairs into fixed mount-root target paths."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        """Check out `url` at `commit` into `dest`, atomically.

        Idempotent: a no-op when `dest` already exists at `commit`. Refuses
        to touch a dirty checkout or a linked worktree at `dest`, raising
        `CheckoutError` instead of destroying local state. Otherwise clones
        to a temporary directory beside `dest` and atomically `os.replace`s
        it into place — no half-cloned directory is ever left at `dest` on
        failure.
        """
        if dest.exists():
            if _is_linked_worktree(dest):
                raise CheckoutError(f"refusing to touch linked worktree at {dest}")

            current_head = self._current_head(dest)
            if current_head == commit:
                return  # idempotent no-op

            if self._is_dirty(dest):
                raise CheckoutError(f"refusing to overwrite dirty checkout at {dest}")

        self._clone_and_replace(url, commit, dest)

    def scan(self, roots: Sequence[Path]) -> list[ScannedRepo]:
        raise NotImplementedError("scan lands in PR-2b")

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError("promote lands in PR-2b")

    def _clone_and_replace(self, url: str, commit: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(dir=dest.parent)
        clone_path = Path(tmp_dir)
        try:
            self._run(["git", "clone", "--no-checkout", url, str(clone_path)])
            self._run(["git", "-C", str(clone_path), "checkout", "--detach", commit])

            if dest.exists():
                shutil.rmtree(dest)
            os.replace(clone_path, dest)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    def _current_head(self, dest: Path) -> str:
        result = self._run(["git", "-C", str(dest), "rev-parse", "HEAD"])
        return result.stdout.strip()

    def _is_dirty(self, dest: Path) -> bool:
        result = self._run(["git", "-C", str(dest), "status", "--porcelain"])
        return bool(result.stdout.strip())

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
                env=_non_interactive_env(),
            )
        except FileNotFoundError as exc:
            raise CheckoutError(f"git executable not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CheckoutError(f"git command timed out after {self._timeout}s: {argv}") from exc

        if result.returncode != 0:
            raise CheckoutError(f"git command failed ({' '.join(argv)}): {result.stderr.strip()}")

        return result


def _is_linked_worktree(dest: Path) -> bool:
    """A linked `git worktree` has a `.git` FILE (pointing to the main repo's
    `.git/worktrees/...`), never a `.git` directory like a normal checkout."""
    git_path = dest / ".git"
    return git_path.is_file()


__all__ = ["GitWorkspaceProvider"]
