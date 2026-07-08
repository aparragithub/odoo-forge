import subprocess

import pytest

from odoo_forge.manifest.errors import (
    AuthenticationError,
    NetworkError,
    RefNotFoundError,
    ResolutionError,
)
from odoo_forge.ports.source_provider import SourceProvider
from odoo_forge_git.git_provider import GitSourceProvider

URL = "https://github.com/odoo/odoo.git"
BARE_SHA = "a" * 40


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_bare_sha_passthrough_no_subprocess_call(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _fail_if_called(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("subprocess.run must not be called for a bare SHA")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    provider = GitSourceProvider()
    result = provider.resolve_ref(URL, BARE_SHA)

    assert result == BARE_SHA
    assert called is False


def test_branch_ref_resolves_via_ls_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_argv: list[str] = []
    sha = "b" * 40

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        captured_argv.extend(argv)
        return _FakeCompletedProcess(0, stdout=f"{sha}\trefs/heads/main\n")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    result = provider.resolve_ref(URL, "main")

    assert result == sha
    assert captured_argv == ["git", "ls-remote", URL, "main"]


def test_peeled_tag_preferred_over_lightweight(monkeypatch: pytest.MonkeyPatch) -> None:
    lightweight_sha = "c" * 40
    peeled_sha = "d" * 40
    stdout = f"{lightweight_sha}\trefs/tags/19.0\n{peeled_sha}\trefs/tags/19.0^{{}}\n"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    result = provider.resolve_ref(URL, "19.0")

    assert result == peeled_sha


def test_lightweight_tag_used_when_no_peeled(monkeypatch: pytest.MonkeyPatch) -> None:
    sha = "e" * 40
    stdout = f"{sha}\trefs/tags/19.0\n"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    result = provider.resolve_ref(URL, "19.0")

    assert result == sha


def test_empty_output_raises_ref_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(RefNotFoundError) as exc_info:
        provider.resolve_ref(URL, "does-not-exist")

    assert exc_info.value.url == URL
    assert exc_info.value.ref == "does-not-exist"


@pytest.mark.parametrize(
    "stderr",
    [
        "Permission denied (publickey).",
        "fatal: Authentication failed for 'https://example.com/repo.git/'",
        "fatal: could not read Username for 'https://example.com'",
    ],
)
def test_auth_failure_markers_raise_authentication_error(
    monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(128, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(AuthenticationError) as exc_info:
        provider.resolve_ref(URL, "main")

    assert exc_info.value.url == URL


def test_unreachable_remote_raises_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = "fatal: unable to access: Could not resolve host"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(128, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(NetworkError) as exc_info:
        provider.resolve_ref(URL, "main")

    assert exc_info.value.url == URL
    assert exc_info.value.detail == stderr


def test_missing_git_binary_raises_resolution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(ResolutionError):
        provider.resolve_ref(URL, "main")


def test_adapter_satisfies_source_provider_protocol() -> None:
    assert isinstance(GitSourceProvider(), SourceProvider)


def test_ls_remote_timeout_raises_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        timeout = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(
            cmd=argv, timeout=timeout if isinstance(timeout, (int, float)) else 30
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(NetworkError) as exc_info:
        provider.resolve_ref(URL, "main")

    assert exc_info.value.url == URL
    assert "main" in str(exc_info.value)
    assert "timed out" in str(exc_info.value)


def test_ls_remote_disables_interactive_prompts_and_pins_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    sha = "b" * 40

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        captured_kwargs.update(kwargs)
        return _FakeCompletedProcess(0, stdout=f"{sha}\trefs/heads/main\n")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    provider.resolve_ref(URL, "main")

    env = captured_kwargs["env"]
    assert isinstance(env, dict)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["LANG"] == "C"
    assert env["LC_ALL"] == "C"


def test_uppercase_bare_sha_passthrough_no_subprocess_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _fail_if_called(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("subprocess.run must not be called for a bare SHA")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)

    provider = GitSourceProvider()
    sha = "A" * 40
    result = provider.resolve_ref(URL, sha)

    assert result == sha
    assert called is False


def test_branch_preferred_over_peeled_tag_when_names_collide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    branch_sha = "1" * 40
    peeled_sha = "2" * 40
    stdout = f"{branch_sha}\trefs/heads/19.0\n{peeled_sha}\trefs/tags/19.0^{{}}\n"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    result = provider.resolve_ref(URL, "19.0")

    assert result == branch_sha


def test_branch_preferred_over_lightweight_tag_when_names_collide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    branch_sha = "3" * 40
    lightweight_sha = "4" * 40
    stdout = f"{branch_sha}\trefs/heads/19.0\n{lightweight_sha}\trefs/tags/19.0\n"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    result = provider.resolve_ref(URL, "19.0")

    assert result == branch_sha


def test_unclassified_stderr_falls_back_to_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = "fatal: repository 'https://example.com/repo.git/' not found"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(128, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(NetworkError) as exc_info:
        provider.resolve_ref(URL, "main")

    assert exc_info.value.url == URL
    assert exc_info.value.detail == stderr
