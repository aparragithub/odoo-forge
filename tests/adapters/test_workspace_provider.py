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


SECRET_URL = "https://user:secret-token@host/repo.git"


def test_clone_failure_does_not_leak_credential_url_in_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if "clone" in argv:
            return _FakeCompletedProcess(128, stderr="fatal: repository not found")
        return _FakeCompletedProcess(0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError) as excinfo:
        provider.checkout(SECRET_URL, COMMIT, dest)

    message = str(excinfo.value)
    assert "secret-token" not in message
    assert SECRET_URL not in message


def test_clone_returncode_nonzero_raises_checkout_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dest = tmp_path / "custom" / "acme" / "odoo"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        if "clone" in argv:
            return _FakeCompletedProcess(1, stderr="boom")
        return _FakeCompletedProcess(0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitWorkspaceProvider()

    with pytest.raises(CheckoutError):
        provider.checkout(URL, COMMIT, dest)


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

    assert "secret-token" not in str(excinfo.value)


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
        argv for argv in fake_run.calls if "clone" in argv  # type: ignore[attr-defined]
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

    def _flaky_replace(src: object, dst: object) -> None:
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


def test_scan_and_promote_are_not_yet_implemented() -> None:
    """PR-2a scope is `checkout` only — `scan`/`promote` land in PR-2b."""
    provider = GitWorkspaceProvider()

    with pytest.raises(NotImplementedError):
        provider.scan([Path("/mnt/community")])

    with pytest.raises(NotImplementedError):
        provider.promote(Path("/mnt/community/core/odoo"), Path("/mnt/worktrees/core/odoo"), "unlock/core")


def test_adapter_satisfies_workspace_provider_protocol() -> None:
    assert isinstance(GitWorkspaceProvider(), WorkspaceProvider)
