"""Concrete `WorkspaceProvider` adapter backed by `git clone`/`checkout`.

Structurally satisfies `odoo_forge.ports.workspace_provider.WorkspaceProvider`
without importing it — the port stays a pure interface and this adapter is
the only place in the codebase that shells out to `git` for workspace
projection.

`checkout` (PR-2a), `scan`, and `promote` (PR-2b) are all implemented here.
The adapter stays dumb: `scan` returns raw, un-attributed `ScannedRepo`
facts (no layer/mount-root knowledge — that mapping is the pure core
`materialize_state`), and `promote` only executes the worktree move to a
`dest`/`branch` the pure core already decided.
"""

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from odoo_forge.manifest.errors import (
    AlreadyUnlockedError,
    CheckoutError,
    PromotionError,
    ScanError,
    WorkspaceError,
)
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

    def checkout(
        self,
        url: str,
        commit: str,
        dest: Path,
        env_overlay: Mapping[str, str] | None = None,
    ) -> None:
        """Check out `url` at `commit` into `dest`, atomically.

        Idempotent: a no-op when `dest` already exists at `commit`. Refuses
        to touch a dirty checkout or a linked worktree at `dest`, raising
        `CheckoutError` instead of destroying local state. Otherwise clones
        to a temporary directory beside `dest`, then swaps it into place via
        an atomic same-filesystem rename dance: any existing `dest` is first
        renamed to a sibling backup, the fresh clone is `os.replace`d into
        `dest`, and only then is the backup removed. If the final swap fails
        the backup is restored, so `dest` is never left absent or half-cloned.

        `env_overlay` is merged over `_non_interactive_env()` for every git
        subprocess this checkout runs (e.g. a short-lived `GIT_ASKPASS` from
        `GitCredentialInjector`); when `None` the resulting env is
        byte-for-byte identical to today's behavior. Overlay values are
        never logged and never interpolated into any raised error message.
        """
        if dest.exists():
            if _is_linked_worktree(dest):
                raise CheckoutError(f"refusing to touch linked worktree at {dest}")

            current_head = self._current_head(dest)
            if current_head == commit:
                return  # idempotent no-op

            if self._is_dirty(dest):
                raise CheckoutError(f"refusing to overwrite dirty checkout at {dest}")

        self._clone_and_replace(url, commit, dest, env_overlay)

    def scan(self, roots: Sequence[Path]) -> list[ScannedRepo]:
        """Walk `roots` and return one `ScannedRepo` per on-disk git checkout.

        Raw and un-attributed: reads only `path`, `remote.origin.url`, and
        `HEAD` off disk — no layer/mount-root interpretation (that mapping is
        the pure core `materialize_state`). Non-git directories are skipped
        silently; a directory containing `.git` is never recursed into
        further (it is treated as one repo, not walked for nested repos).
        Raises `ScanError` when a found checkout's `HEAD`/remote URL cannot
        be read (e.g. a corrupted repo).
        """
        scanned: list[ScannedRepo] = []
        for root in roots:
            if not root.exists():
                continue
            scanned.extend(self._scan_root(root))
        return scanned

    def _scan_root(self, root: Path) -> list[ScannedRepo]:
        found: list[ScannedRepo] = []
        for dirpath, dirnames, _filenames in os.walk(root):
            current = Path(dirpath)
            if (current / ".git").exists():
                found.append(self._scan_repo(current))
                # A repo's internals are never nested repos; stop descending.
                dirnames[:] = []
        return found

    def _scan_repo(self, path: Path) -> ScannedRepo:
        commit = self._run(
            ["git", "-C", str(path), "rev-parse", "HEAD"], error_cls=ScanError
        ).stdout.strip()
        url = self._run(
            ["git", "-C", str(path), "remote", "get-url", "origin"], error_cls=ScanError
        ).stdout.strip()
        return ScannedRepo(path=path, url=url, commit=commit)

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        """Promote the checkout at `source` to a writable worktree at `dest`.

        `dest` and `branch` are computed by the pure core `unlock` use-case;
        this adapter only executes the move via `git worktree add -b <branch>
        <dest>` from within `source`, leaving `source` itself untouched (its
        originally-locked commit stays recoverable). Raises
        `AlreadyUnlockedError` if `dest` already exists, and `PromotionError`
        if the underlying `git worktree add` fails.
        """
        if dest.exists():
            raise AlreadyUnlockedError(f"'{dest}' is already a writable checkout")

        dest.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            ["git", "-C", str(source), "worktree", "add", "-b", branch, "--", str(dest)],
            error_cls=PromotionError,
        )

    def _clone_and_replace(
        self,
        url: str,
        commit: str,
        dest: Path,
        env_overlay: Mapping[str, str] | None = None,
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(dir=dest.parent)
        clone_path = Path(tmp_dir)
        try:
            self._clone(url, clone_path, env_overlay)
            # `git checkout` has no clean end-of-options form for a revision,
            # so we rely on `commit` already being a resolved 40-char SHA and
            # pass `--detach` to keep the checkout headless.
            self._run(
                ["git", "-C", str(clone_path), "checkout", "--detach", commit],
                env_overlay=env_overlay,
            )
            self._atomic_swap(clone_path, dest)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    def _clone(
        self, url: str, clone_path: Path, env_overlay: Mapping[str, str] | None = None
    ) -> None:
        """Clone `url` into `clone_path`, preferring a partial clone.

        Attempts `git clone --filter=blob:none --no-checkout` first, so only
        the commit/tree graph is fetched and blobs are lazily fetched later
        by `checkout`. If the remote does not support the filter (or any
        other clone failure occurs), `clone_path` is removed and a single
        full-clone retry (`--no-checkout`, no `--filter`) is attempted. `git
        clone` requires an empty/absent target, so `clone_path` must not
        exist when the retry runs. A second failure propagates unchanged.
        """
        # `--` marks end-of-options so a `url`/`dest` beginning with `-`
        # is always treated as a positional, never a git flag.
        try:
            self._run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    "--",
                    url,
                    str(clone_path),
                ],
                env_overlay=env_overlay,
            )
            return
        except CheckoutError:
            pass

        # Retry outside the `except` block so a second failure does not
        # implicitly chain onto the first via `__context__`.
        shutil.rmtree(clone_path, ignore_errors=True)
        self._run(
            ["git", "clone", "--no-checkout", "--", url, str(clone_path)],
            env_overlay=env_overlay,
        )

    @staticmethod
    def _atomic_swap(clone_path: Path, dest: Path) -> None:
        """Move `clone_path` onto `dest` without ever leaving `dest` absent."""
        backup_path: Path | None = None
        temp_dir: Path | None = None
        if dest.exists():
            # Reserve a guaranteed-free sibling path on the same filesystem.
            # Move `dest` into the temp directory to avoid TOCTOU race:
            # the directory remains exclusively-owned the whole time.
            reserved = tempfile.mkdtemp(dir=dest.parent)
            temp_dir = Path(reserved)
            backup_path = temp_dir / dest.name
            os.replace(dest, backup_path)

        try:
            os.replace(clone_path, dest)
        except BaseException:
            if backup_path is not None:
                os.replace(backup_path, dest)
            shutil.rmtree(clone_path, ignore_errors=True)
            raise

        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _current_head(self, dest: Path) -> str:
        result = self._run(["git", "-C", str(dest), "rev-parse", "HEAD"])
        return result.stdout.strip()

    def _is_dirty(self, dest: Path) -> bool:
        result = self._run(["git", "-C", str(dest), "status", "--porcelain"])
        return bool(result.stdout.strip())

    def _run(
        self,
        argv: list[str],
        error_cls: type[WorkspaceError] = CheckoutError,
        env_overlay: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        timeout_error: WorkspaceError | None = None
        env = {**_non_interactive_env(), **(env_overlay or {})}
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
                env=env,
            )
        except FileNotFoundError as exc:
            raise error_cls(f"git executable not found: {exc}") from exc
        except subprocess.TimeoutExpired:
            # Never splat argv/url into the message — the clone URL may embed
            # `user:token@` credentials. A safe subcommand label is enough.
            timeout_error = error_cls(
                f"git {_git_subcommand(argv)} timed out after {self._timeout}s"
            )
        else:
            if result.returncode != 0:
                # Git stderr is untrusted and may repeat credential-bearing remotes.
                raise error_cls(
                    f"git {_git_subcommand(argv)} failed with exit code {result.returncode}"
                )

            return result

        raise timeout_error from None


def _git_subcommand(argv: Sequence[str]) -> str:
    """Extract a safe subcommand label (e.g. `clone`) from a git argv.

    Skips the `git` binary and any global `-C <path>` prefix so the label
    never includes the credentialed clone URL or other positionals.
    """
    tokens = list(argv)
    i = 1 if tokens and tokens[0] == "git" else 0
    while i < len(tokens):
        token = tokens[i]
        if token == "-C":
            i += 2  # skip the flag and its path argument
            continue
        if token.startswith("-"):
            i += 1
            continue
        return token
    return "command"


def _is_linked_worktree(dest: Path) -> bool:
    """A linked `git worktree` has a `.git` FILE (pointing to the main repo's
    `.git/worktrees/...`), never a `.git` directory like a normal checkout."""
    git_path = dest / ".git"
    return git_path.is_file()


__all__ = ["GitWorkspaceProvider"]
