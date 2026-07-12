import subprocess
import traceback
from pathlib import Path

import pytest

from odoo_forge.manifest.errors import (
    AlreadyUnlockedError,
    CheckoutError,
    PromotionError,
    ScanError,
)
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

    fake_run = _fake_run_factory(rev_parse_output=OTHER_COMMIT, status_output=" M some/file.py\n")
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError):
        provider.checkout(URL, COMMIT, dest)

    argv_joined = [" ".join(argv) for argv in fake_run.calls]  # type: ignore[attr-defined]
    assert not any("clone" in argv for argv in argv_joined)
    assert dest.exists()  # never destroyed


def test_checkout_refuses_linked_worktree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


SECRET_URL = "https://user:secret-token@host/repo.git"


@pytest.mark.parametrize(
    "stderr, secrets",
    [
        (
            "fatal: unable to access 'https://user:password@host/repo.git/'",
            ("user", "password", "https://user:password@host/repo.git"),
        ),
        (
            "remote: authentication failed for token ghp_0123456789abcdef",
            ("ghp_0123456789abcdef",),
        ),
        (
            "fatal: repository 'https://oauth2:access-token@example.com/repo.git' not found",
            ("oauth2", "access-token", "https://oauth2:access-token@example.com/repo.git"),
        ),
    ],
)
def test_clone_failure_does_not_expose_untrusted_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stderr: str,
    secrets: tuple[str, ...],
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if "clone" in argv:
            return _FakeCompletedProcess(128, stderr=stderr)
        return _FakeCompletedProcess(0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError) as excinfo:
        provider.checkout(SECRET_URL, COMMIT, dest)

    message = str(excinfo.value)
    assert message == "git clone failed with exit code 128"
    assert all(secret not in message for secret in secrets)
    assert SECRET_URL not in message


def test_clone_returncode_nonzero_has_bounded_useful_diagnostic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if "clone" in argv:
            return _FakeCompletedProcess(1, stderr="boom")
        return _FakeCompletedProcess(0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError) as excinfo:
        provider.checkout(URL, COMMIT, dest)

    assert str(excinfo.value) == "git clone failed with exit code 1"


def test_timeout_raises_checkout_error_without_leaking_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        raise subprocess.TimeoutExpired(cmd=list(argv), timeout=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError) as excinfo:
        provider.checkout(SECRET_URL, COMMIT, dest)

    assert str(excinfo.value) == "git clone timed out after 60s"
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None
    rendered_traceback = "".join(
        traceback.format_exception(excinfo.type, excinfo.value, excinfo.tb)
    )
    assert SECRET_URL not in rendered_traceback
    assert "secret-token" not in rendered_traceback


def test_clone_passes_url_as_positional_after_end_of_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    hostile_url = "--upload-pack=evil"
    fake_run = _fake_run_factory(rev_parse_output=COMMIT)
    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = GitWorkspaceProvider()
    provider.checkout(hostile_url, COMMIT, dest)

    clone_argv = next(
        argv
        for argv in fake_run.calls  # type: ignore[attr-defined]
        if "clone" in argv
    )
    assert "--" in clone_argv
    assert clone_argv.index("--") < clone_argv.index(hostile_url)


def test_clone_failure_cleans_up_temp_and_preserves_existing_dest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()
    (dest / "keep.txt").write_text("original")

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if "rev-parse" in argv:
            return _FakeCompletedProcess(0, stdout=f"{OTHER_COMMIT}\n")
        if "status" in argv:
            return _FakeCompletedProcess(0, stdout="")
        if "clone" in argv:
            return _FakeCompletedProcess(128, stderr="fatal: nope")
        return _FakeCompletedProcess(0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError):
        provider.checkout(URL, COMMIT, dest)

    # existing clean dest preserved on clone failure
    assert (dest / "keep.txt").read_text() == "original"
    # no leftover temp sibling
    siblings = [p for p in dest.parent.iterdir() if p != dest]
    assert siblings == []


def test_final_replace_failure_restores_original_dest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os as _os

    dest = tmp_path / "custom" / "acme" / "odoo"
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()
    (dest / "keep.txt").write_text("original")

    fake_run = _fake_run_factory(rev_parse_output=OTHER_COMMIT, status_output="")
    monkeypatch.setattr(subprocess, "run", fake_run)

    real_replace = _os.replace
    failed_once = {"done": False}

    def _flaky_replace(src: str | Path, dst: str | Path) -> None:
        # Fail only the first clone->dest swap; allow the backup->dest restore.
        if Path(dst) == dest and not failed_once["done"]:
            failed_once["done"] = True
            raise OSError("simulated replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(_os, "replace", _flaky_replace)

    provider = GitWorkspaceProvider()

    with pytest.raises((CheckoutError, OSError)):
        provider.checkout(URL, COMMIT, dest)

    assert dest.exists()
    assert (dest / "keep.txt").read_text() == "original"


def test_adapter_satisfies_workspace_provider_protocol() -> None:
    assert isinstance(GitWorkspaceProvider(), WorkspaceProvider)


class TestScan:
    def test_scan_reads_head_and_remote_url_skips_non_git_dirs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "custom"
        repo_dir = root / "custom-x" / "odoo-partner"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()
        # Sibling non-git directory must be skipped, not raise.
        (root / "custom-x" / "not-a-repo").mkdir(parents=True)
        (root / "custom-x" / "not-a-repo" / "readme.txt").write_text("hi")

        def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
            if "rev-parse" in argv:
                return _FakeCompletedProcess(0, stdout=f"{COMMIT}\n")
            if "get-url" in argv:
                return _FakeCompletedProcess(0, stdout=f"{URL}\n")
            return _FakeCompletedProcess(0, stdout="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        provider = GitWorkspaceProvider()
        scanned = provider.scan([root])

        assert len(scanned) == 1
        assert scanned[0].path == repo_dir
        assert scanned[0].url == URL
        assert scanned[0].commit == COMMIT

    def test_scan_skips_nonexistent_root(self, tmp_path: Path) -> None:
        provider = GitWorkspaceProvider()

        assert provider.scan([tmp_path / "does-not-exist"]) == []

    def test_scan_raises_scan_error_on_corrupted_head(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "custom"
        repo_dir = root / "custom-x" / "odoo-partner"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()

        def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
            if "rev-parse" in argv:
                return _FakeCompletedProcess(128, stderr="fatal: not a valid object name HEAD")
            return _FakeCompletedProcess(0, stdout="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        provider = GitWorkspaceProvider()

        with pytest.raises(ScanError):
            provider.scan([root])

    def test_scan_does_not_leak_credential_url_in_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        root = tmp_path / "custom"
        repo_dir = root / "custom-x" / "odoo-partner"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()

        def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
            if "rev-parse" in argv:
                return _FakeCompletedProcess(0, stdout=f"{COMMIT}\n")
            if "get-url" in argv:
                return _FakeCompletedProcess(128, stderr="fatal: no such remote 'origin'")
            return _FakeCompletedProcess(0, stdout="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        provider = GitWorkspaceProvider()

        with pytest.raises(ScanError) as excinfo:
            provider.scan([root])

        assert SECRET_URL not in str(excinfo.value)


class TestPromote:
    def test_promote_creates_worktree_and_raises_if_already_writable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        source = tmp_path / "custom" / "custom-x" / "odoo-partner"
        source.mkdir(parents=True)
        (source / ".git").mkdir()
        dest = tmp_path / "worktrees" / "custom-x" / "odoo-partner"

        calls: list[list[str]] = []

        def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
            calls.append(list(argv))
            return _FakeCompletedProcess(0, stdout="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        provider = GitWorkspaceProvider()
        provider.promote(source, dest, "unlock/custom-x/odoo-partner")

        assert any("worktree" in argv and "add" in argv for argv in calls)
        assert any("-b" in argv and "unlock/custom-x/odoo-partner" in argv for argv in calls)

        # Re-unlocking a repo that is already a writable worktree fails loud
        # without invoking `git worktree add` again.
        dest.mkdir(parents=True)
        calls.clear()

        with pytest.raises(AlreadyUnlockedError):
            provider.promote(source, dest, "unlock/custom-x/odoo-partner")

        assert calls == []

    def test_promote_failure_raises_promotion_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        source = tmp_path / "custom" / "custom-x" / "odoo-partner"
        source.mkdir(parents=True)
        dest = tmp_path / "worktrees" / "custom-x" / "odoo-partner"

        def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
            return _FakeCompletedProcess(128, stderr="fatal: could not create worktree")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        provider = GitWorkspaceProvider()

        with pytest.raises(PromotionError):
            provider.promote(source, dest, "unlock/custom-x/odoo-partner")
