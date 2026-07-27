import subprocess
from pathlib import Path

import pytest

from odoo_forge_git.git_provider import GitSourceProvider


def _run_git(*argv: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _create_local_repositories(root: Path) -> tuple[Path, Path, str]:
    working_repository = root / "local repository"
    working_repository.mkdir()
    _run_git("init", "-b", "main", cwd=working_repository)
    _run_git("config", "user.email", "tests@example.com", cwd=working_repository)
    _run_git("config", "user.name", "Git Tests", cwd=working_repository)
    (working_repository / "README.md").write_text("initial\n")
    _run_git("add", "README.md", cwd=working_repository)
    _run_git("commit", "-m", "initial", cwd=working_repository)
    commit = _run_git("rev-parse", "HEAD", cwd=working_repository)

    bare_repository = root / "bare remote.git"
    _run_git("clone", "--bare", str(working_repository), str(bare_repository))
    return bare_repository, working_repository, commit


@pytest.mark.integration
def test_local_repository_resolution_uses_real_ls_remote(tmp_path: Path) -> None:
    bare_repository, _working_repository, commit = _create_local_repositories(tmp_path)

    assert GitSourceProvider().resolve_ref(str(bare_repository), "main") == commit


@pytest.mark.integration
@pytest.mark.parametrize("dirty_state", ["staged", "unstaged", "untracked"])
def test_local_repository_resolution_does_not_depend_on_worktree_cleanliness(
    tmp_path: Path, dirty_state: str
) -> None:
    bare_repository, working_repository, commit = _create_local_repositories(tmp_path)

    if dirty_state == "staged":
        (working_repository / "README.md").write_text("staged\n")
        _run_git("add", "README.md", cwd=working_repository)
    elif dirty_state == "unstaged":
        (working_repository / "README.md").write_text("unstaged\n")
    else:
        (working_repository / "untracked.txt").write_text("untracked\n")

    provider = GitSourceProvider()
    assert provider.resolve_ref(str(working_repository), "main") == commit
    assert provider.resolve_ref(str(bare_repository), "main") == commit


@pytest.mark.integration
def test_local_repository_branch_precedes_annotated_tag(tmp_path: Path) -> None:
    bare_repository, repository, branch_commit = _create_local_repositories(tmp_path)

    (repository / "tag.txt").write_text("tag\n")
    _run_git("add", "tag.txt", cwd=repository)
    _run_git("commit", "-m", "tag target", cwd=repository)
    tag_commit = _run_git("rev-parse", "HEAD", cwd=repository)
    _run_git("tag", "-a", "release", "-m", "release", cwd=repository)
    _run_git("update-ref", "refs/heads/release", branch_commit, cwd=repository)
    _run_git("push", str(bare_repository), "--all", cwd=repository)
    _run_git("push", str(bare_repository), "--tags", cwd=repository)

    assert GitSourceProvider().resolve_ref(str(bare_repository), "release") == branch_commit
    assert tag_commit != branch_commit
