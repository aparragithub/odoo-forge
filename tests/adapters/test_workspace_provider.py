import subprocess
from pathlib import Path

import pytest

from odoo_forge.manifest.errors import CheckoutError
from odoo_forge.ports.workspace_provider import WorkspaceProvider
from odoo_forge_workspace.provider import GitWorkspaceProvider

URL = "https://github.com/odoo/odoo.git"
COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_run_factory(rev_parse_output: str, status_output: str = "") -> object:
    """Build a fake `subprocess.run` that answers `rev-parse`/`status`/`clone`/`checkout`."""
    calls: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(list(argv))
        if "rev-parse" in argv:
            return _FakeCompletedProcess(0, stdout=f"{rev_parse_output}\n")
        if "status" in argv:
            return _FakeCompletedProcess(0, stdout=status_output)
        return _FakeCompletedProcess(0, stdout="")

    _fake_run.calls = calls  # type: ignore[attr-defined]
    return _fake_run


def test_checkout_clones_to_temp_and_replaces_into_dest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    fake_run = _fake_run_factory(rev_parse_output=COMMIT)
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()
    provider.checkout(URL, COMMIT, dest)

    argv_joined = [" ".join(argv) for argv in fake_run.calls]  # type: ignore[attr-defined]
    assert any("clone" in argv for argv in argv_joined)
    assert any("checkout" in argv for argv in argv_joined)
    assert dest.exists()
    assert (dest / ".marker").exists() is False  # sanity: real dir, not a leftover temp file


def test_checkout_skips_when_head_already_matches_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()

    fake_run = _fake_run_factory(rev_parse_output=COMMIT)
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()
    provider.checkout(URL, COMMIT, dest)

    argv_joined = [" ".join(argv) for argv in fake_run.calls]  # type: ignore[attr-defined]
    assert not any("clone" in argv for argv in argv_joined)


def test_checkout_refuses_dirty_existing_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()

    fake_run = _fake_run_factory(
        rev_parse_output=OTHER_COMMIT, status_output=" M some/file.py\n"
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError):
        provider.checkout(URL, COMMIT, dest)

    argv_joined = [" ".join(argv) for argv in fake_run.calls]  # type: ignore[attr-defined]
    assert not any("clone" in argv for argv in argv_joined)
    assert dest.exists()  # never destroyed


def test_checkout_refuses_linked_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    dest.mkdir(parents=True)
    (dest / ".git").write_text("gitdir: /mnt/community/core/odoo/.git/worktrees/odoo\n")

    fake_run = _fake_run_factory(rev_parse_output=OTHER_COMMIT)
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError):
        provider.checkout(URL, COMMIT, dest)

    argv_joined = [" ".join(argv) for argv in fake_run.calls]  # type: ignore[attr-defined]
    assert not any("clone" in argv for argv in argv_joined)
    assert dest.exists()  # never destroyed


def test_checkout_replaces_existing_clean_checkout_at_wrong_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()
    (dest / "stale-marker.txt").write_text("stale")

    fake_run = _fake_run_factory(rev_parse_output=OTHER_COMMIT, status_output="")
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()
    provider.checkout(URL, COMMIT, dest)

    argv_joined = [" ".join(argv) for argv in fake_run.calls]  # type: ignore[attr-defined]
    assert any("clone" in argv for argv in argv_joined)
    assert not (dest / "stale-marker.txt").exists()


def test_missing_git_binary_raises_checkout_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"

    def _fake_run(argv: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError):
        provider.checkout(URL, COMMIT, dest)


def test_scan_and_promote_are_not_yet_implemented() -> None:
    """PR-2a scope is `checkout` only — `scan`/`promote` land in PR-2b."""
    provider = GitWorkspaceProvider()

    with pytest.raises(NotImplementedError):
        provider.scan([Path("/mnt/community")])

    with pytest.raises(NotImplementedError):
        provider.promote(Path("/mnt/community/core/odoo"), Path("/mnt/worktrees/core/odoo"), "unlock/core")


def test_adapter_satisfies_workspace_provider_protocol() -> None:
    assert isinstance(GitWorkspaceProvider(), WorkspaceProvider)
