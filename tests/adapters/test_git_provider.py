import subprocess
import traceback
from typing import cast

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
SECRET_URL = "https://build-user:ghp_super-secret-token@example.com/private/repo.git"
SECRET_SSH_URL = "ssh://deploy-user:ssh-super-secret@example.com:2222/private/repo.git"
SECRETS = ("build-user", "ghp_super-secret-token", SECRET_URL, "raw-stderr-secret")
BARE_SHA = "a" * 40


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _assert_safe_error(error: BaseException, *extra_secrets: str) -> None:
    public_values = [str(error), *map(str, vars(error).values())]
    rendered = "".join(traceback.format_exception(error))
    for secret in (*SECRETS, *extra_secrets):
        assert all(secret not in value for value in public_values)
        assert secret not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None


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
    assert exc_info.value.detail == "git ls-remote failed with exit code 128"


def test_network_failure_projects_credential_safe_bounded_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = f"fatal: unable to access '{SECRET_URL}': raw-stderr-secret"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(128, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(NetworkError) as exc_info:
        GitSourceProvider().resolve_ref(SECRET_URL, "main")

    _assert_safe_error(exc_info.value)
    assert exc_info.value.url == "https://example.com/private/repo.git"
    assert exc_info.value.detail == "git ls-remote failed with exit code 128"


@pytest.mark.parametrize(
    ("result", "error_type"),
    [
        (_FakeCompletedProcess(128, stderr="fatal: Authentication failed"), AuthenticationError),
        (_FakeCompletedProcess(0, stdout=""), RefNotFoundError),
    ],
)
def test_typed_failures_project_credential_safe_url(
    monkeypatch: pytest.MonkeyPatch,
    result: _FakeCompletedProcess,
    error_type: type[ResolutionError],
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)

    with pytest.raises(error_type) as exc_info:
        GitSourceProvider().resolve_ref(SECRET_URL, "main")

    _assert_safe_error(exc_info.value)
    typed_error = cast(AuthenticationError | RefNotFoundError, exc_info.value)
    assert typed_error.url == "https://example.com/private/repo.git"


@pytest.mark.parametrize(
    ("result", "error_type"),
    [
        (_FakeCompletedProcess(128, stderr="fatal: Authentication failed"), AuthenticationError),
        (_FakeCompletedProcess(128, stderr="fatal: transport failed"), NetworkError),
        (_FakeCompletedProcess(0, stdout=""), RefNotFoundError),
    ],
)
def test_ssh_uri_typed_failures_redact_userinfo(
    monkeypatch: pytest.MonkeyPatch,
    result: _FakeCompletedProcess,
    error_type: type[ResolutionError],
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)

    with pytest.raises(error_type) as exc_info:
        GitSourceProvider().resolve_ref(SECRET_SSH_URL, "main")

    _assert_safe_error(exc_info.value, "deploy-user", "ssh-super-secret", SECRET_SSH_URL)
    typed_error = cast(AuthenticationError | NetworkError | RefNotFoundError, exc_info.value)
    assert typed_error.url == "ssh://example.com:2222/private/repo.git"


@pytest.mark.parametrize(
    ("remote", "safe_remote", "secrets"),
    [
        (
            "deploy-secret@example.com:private/repo.git",
            "example.com:private/repo.git",
            ("deploy-secret",),
        ),
        (
            "ssh://deploy-user:ssh-super-secret@[broken/repo.git",
            "<redacted-remote>",
            ("deploy-user", "ssh-super-secret"),
        ),
    ],
)
def test_nonstandard_remotes_fail_safely_without_credential_leaks(
    monkeypatch: pytest.MonkeyPatch,
    remote: str,
    safe_remote: str,
    secrets: tuple[str, ...],
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompletedProcess(128, stderr="fatal: transport failed"),
    )

    with pytest.raises(NetworkError) as exc_info:
        GitSourceProvider().resolve_ref(remote, "main")

    _assert_safe_error(exc_info.value, remote, *secrets)
    assert exc_info.value.url == safe_remote


def test_missing_git_binary_raises_resolution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()

    with pytest.raises(ResolutionError):
        provider.resolve_ref(URL, "main")


def test_missing_git_binary_does_not_retain_secret_exception_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        error = FileNotFoundError(f"missing executable for {argv!r}: raw-stderr-secret")
        error.filename = SECRET_URL
        raise error

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(ResolutionError) as exc_info:
        GitSourceProvider().resolve_ref(SECRET_URL, "main")

    _assert_safe_error(exc_info.value)
    assert str(exc_info.value) == "git executable not found"


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


def test_timeout_does_not_retain_secret_argv_or_exception_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(argv: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            cmd=[*argv, "raw-stderr-secret"], timeout=cast(float, kwargs["timeout"])
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(NetworkError) as exc_info:
        GitSourceProvider(timeout=1.25).resolve_ref(SECRET_URL, "main")

    _assert_safe_error(exc_info.value)
    assert exc_info.value.url == "https://example.com/private/repo.git"
    assert exc_info.value.detail == "ref 'main': timed out after 1.25s"


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
    assert env["GIT_ASKPASS"] == ""
    assert env["LANG"] == "C"
    assert env["LC_ALL"] == "C"
    assert captured_kwargs["timeout"] == 30
    assert captured_kwargs["capture_output"] is True
    assert captured_kwargs["text"] is True
    assert captured_kwargs["check"] is False


def test_env_overlay_merges_over_non_interactive_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    sha = "b" * 40

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        captured_kwargs.update(kwargs)
        return _FakeCompletedProcess(0, stdout=f"{sha}\trefs/heads/main\n")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    provider = GitSourceProvider()
    provider.resolve_ref(URL, "main", env_overlay={"GIT_ASKPASS": "/tmp/askpass.py"})

    env = captured_kwargs["env"]
    assert isinstance(env, dict)
    assert env["GIT_ASKPASS"] == "/tmp/askpass.py"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["LANG"] == "C"


def test_no_env_overlay_preserves_exact_current_env(
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
    assert env["GIT_ASKPASS"] == ""
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_env_overlay_secret_never_leaks_into_error_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "askpass-injected-secret-marker"

    def _fake_run(argv: list[str], **kwargs: object) -> _FakeCompletedProcess:
        env = kwargs.get("env")
        assert isinstance(env, dict)
        assert env["GIT_ASKPASS_SECRET_MARKER"] == secret
        return _FakeCompletedProcess(128, stderr="fatal: Authentication failed")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(AuthenticationError) as exc_info:
        GitSourceProvider().resolve_ref(
            SECRET_URL, "main", env_overlay={"GIT_ASKPASS_SECRET_MARKER": secret}
        )

    _assert_safe_error(exc_info.value, secret)


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
    assert exc_info.value.detail == "git ls-remote failed with exit code 128"


@pytest.mark.parametrize(
    ("result", "error_type"),
    [
        (_FakeCompletedProcess(0, stdout=""), RefNotFoundError),
        (_FakeCompletedProcess(128, stderr="fatal: Authentication failed"), AuthenticationError),
        (_FakeCompletedProcess(128, stderr="fatal: Could not resolve host"), NetworkError),
        (
            _FakeCompletedProcess(128, stderr="fatal: couldn't find remote ref missing"),
            RefNotFoundError,
        ),
        (
            _FakeCompletedProcess(
                128,
                stderr="fatal: Authentication failed: couldn't find remote ref missing",
            ),
            AuthenticationError,
        ),
        (
            _FakeCompletedProcess(
                128,
                stderr="fatal: network failure while couldn't find remote ref missing",
            ),
            NetworkError,
        ),
    ],
)
def test_ls_remote_classification_matrix_preserves_safe_public_projection(
    monkeypatch: pytest.MonkeyPatch,
    result: _FakeCompletedProcess,
    error_type: type[RefNotFoundError | AuthenticationError | NetworkError],
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)

    with pytest.raises(error_type) as exc_info:
        GitSourceProvider().resolve_ref(SECRET_URL, "missing")

    _assert_safe_error(exc_info.value)
    assert isinstance(exc_info.value, (RefNotFoundError, AuthenticationError, NetworkError))
    assert exc_info.value.url == "https://example.com/private/repo.git"
