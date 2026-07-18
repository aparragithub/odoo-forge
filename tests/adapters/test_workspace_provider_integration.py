"""Real-git hermetic evidence for `GitWorkspaceProvider`'s partial-clone path.

No mocking: spawns a real `git` subprocess against local `file://` bare
repositories, so it also proves the adapter's real argv (not a mocked stand-in)
produces a correct materialized tree via `checkout` and `promote`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from odoo_forge_workspace.provider import GitWorkspaceProvider

pytestmark = pytest.mark.integration


def _git(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, check=False)


def _require_git() -> None:
    try:
        result = _git(["--version"])
    except FileNotFoundError:
        pytest.skip("git prerequisite unavailable: executable not found")
    if result.returncode != 0:
        pytest.skip("git prerequisite unavailable: `git --version` failed")

    # Typical output: "git version 2.34.1"
    parts = result.stdout.strip().split()
    version_str = parts[2] if len(parts) >= 3 else ""
    digits = [p for p in version_str.split(".")[:2] if p.isdigit()]
    version_tuple = tuple(int(p) for p in digits)
    if len(version_tuple) < 2 or version_tuple < (2, 19):
        pytest.skip(f"git prerequisite unavailable: version {version_str!r} < 2.19")


def _make_bare_repo_with_commit(
    tmp_path: Path, name: str, *, allow_filter: bool
) -> tuple[Path, str]:
    """Build a bare repo with one real commit; return (bare path, commit SHA)."""
    bare = tmp_path / f"{name}.git"
    work = tmp_path / f"{name}-work"
    bare.mkdir()
    assert _git(["init", "--bare", "-q"], cwd=bare).returncode == 0
    if allow_filter:
        assert _git(["config", "uploadpack.allowFilter", "true"], cwd=bare).returncode == 0

    assert _git(["clone", "-q", str(bare), str(work)]).returncode == 0
    assert _git(["config", "user.email", "test@example.com"], cwd=work).returncode == 0
    assert _git(["config", "user.name", "Test"], cwd=work).returncode == 0
    (work / "README.md").write_text(f"partial clone fixture: {name}\n")
    assert _git(["add", "."], cwd=work).returncode == 0
    assert _git(["commit", "-q", "-m", "init"], cwd=work).returncode == 0
    assert _git(["push", "-q", "origin", "HEAD:refs/heads/main"], cwd=work).returncode == 0

    sha = _git(["rev-parse", "HEAD"], cwd=work).stdout.strip()
    assert sha
    return bare, sha


class TestPartialCloneWithAllowFilter:
    """Fixture A: remote advertises `uploadpack.allowFilter`."""

    def test_checkout_and_promote_materialize_correct_tree(self, tmp_path: Path) -> None:
        _require_git()
        bare, sha = _make_bare_repo_with_commit(tmp_path, "allow-filter", allow_filter=True)
        url = f"file://{bare}"
        dest = tmp_path / "checkouts" / "allow-filter"

        provider = GitWorkspaceProvider()
        provider.checkout(url, sha, dest)

        assert (dest / "README.md").read_text() == "partial clone fixture: allow-filter\n"
        assert _git(["rev-parse", "HEAD"], cwd=dest).stdout.strip() == sha

        worktree_dest = tmp_path / "worktrees" / "allow-filter"
        provider.promote(dest, worktree_dest, "unlock/allow-filter")

        assert (worktree_dest / "README.md").read_text() == "partial clone fixture: allow-filter\n"
        assert _git(["rev-parse", "HEAD"], cwd=worktree_dest).stdout.strip() == sha


class TestFullCloneFallbackWithoutAllowFilter:
    """Fixture B: remote does NOT advertise `uploadpack.allowFilter`.

    Empirically (git 2.55, local `file://` transport), an unsupported
    `--filter` is not always a hard clone error — git may instead print a
    warning ("filtering not recognized by server, ignoring") and complete
    the clone anyway, without ever exercising our `_clone` fallback branch.
    So this fixture asserts the OUTCOME (a correct, offline-materialized
    tree) rather than which specific clone attempt (filtered or full)
    succeeded — it stays robust across git versions/transports whether or
    not the fallback branch itself is exercised.
    """

    def test_checkout_still_succeeds_and_materializes_correct_tree(self, tmp_path: Path) -> None:
        _require_git()
        bare, sha = _make_bare_repo_with_commit(tmp_path, "no-allow-filter", allow_filter=False)
        url = f"file://{bare}"
        dest = tmp_path / "checkouts" / "no-allow-filter"

        provider = GitWorkspaceProvider()
        provider.checkout(url, sha, dest)

        assert (dest / "README.md").read_text() == "partial clone fixture: no-allow-filter\n"
        assert _git(["rev-parse", "HEAD"], cwd=dest).stdout.strip() == sha
