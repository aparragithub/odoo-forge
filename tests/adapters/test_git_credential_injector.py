"""RED-first tests for the shared askpass-based `GitCredentialInjector`."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

from odoo_forge.credentials.types import CredentialHandle, CredentialInjectionDescriptor
from odoo_forge_git.git_credential_injector import GitCredentialInjector

_MARKER_SECRET = "marker-secret-2c8f1e7a"


def _descriptor() -> CredentialInjectionDescriptor:
    return CredentialInjectionDescriptor(
        handle=CredentialHandle("enterprise/source-git"),
        target_kind="source",
        store_ref="sops://enterprise/source-git",
        redaction_label="SOPS credential",
    )


def _fake_resolver(_handle: CredentialHandle) -> str:
    return _MARKER_SECRET


def test_askpass_script_created_with_0700_permissions() -> None:
    injector = GitCredentialInjector()
    captured_script: Path | None = None
    with injector.askpass_env(_descriptor(), _fake_resolver) as env:
        script_path = Path(env["GIT_ASKPASS"])
        captured_script = script_path
        mode = stat.S_IMODE(script_path.stat().st_mode)
        assert mode == 0o700
    assert captured_script is not None
    assert not captured_script.exists()


def test_askpass_script_emits_secret_on_stdout_when_invoked() -> None:
    injector = GitCredentialInjector()
    with injector.askpass_env(_descriptor(), _fake_resolver) as env:
        script_path = Path(env["GIT_ASKPASS"])
        result = subprocess.run(
            [sys.executable, str(script_path), "Username for 'https://example.com':"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == _MARKER_SECRET


def test_git_terminal_prompt_disabled_in_env_overlay() -> None:
    injector = GitCredentialInjector()
    with injector.askpass_env(_descriptor(), _fake_resolver) as env:
        assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_script_removed_after_normal_exit() -> None:
    injector = GitCredentialInjector()
    with injector.askpass_env(_descriptor(), _fake_resolver) as env:
        script_path = Path(env["GIT_ASKPASS"])
        assert script_path.exists()
    assert not script_path.exists()


def test_script_removed_even_when_wrapped_block_raises() -> None:
    injector = GitCredentialInjector()
    script_path: Path | None = None
    with (
        pytest.raises(RuntimeError),
        injector.askpass_env(_descriptor(), _fake_resolver) as env,
    ):
        script_path = Path(env["GIT_ASKPASS"])
        assert script_path.exists()
        raise RuntimeError("simulated failure inside the wrapped git call")
    assert script_path is not None
    assert not script_path.exists()


def test_secret_never_appears_in_exception_message_raised_through_contextmanager() -> None:
    injector = GitCredentialInjector()
    with (
        pytest.raises(RuntimeError) as exc_info,
        injector.askpass_env(_descriptor(), _fake_resolver),
    ):
        raise RuntimeError("boom while fetching")
    assert _MARKER_SECRET not in str(exc_info.value)


def test_secret_never_appears_in_env_values_other_than_the_script_content() -> None:
    injector = GitCredentialInjector()
    with injector.askpass_env(_descriptor(), _fake_resolver) as env:
        for key, value in env.items():
            if key == "GIT_ASKPASS":
                continue
            assert _MARKER_SECRET not in value


def test_askpass_script_is_single_use_marker_present_only_within_context() -> None:
    injector = GitCredentialInjector()
    with injector.askpass_env(_descriptor(), _fake_resolver) as first_env:
        first_script = Path(first_env["GIT_ASKPASS"])
        assert first_script.exists()
    with injector.askpass_env(_descriptor(), _fake_resolver) as second_env:
        second_script = Path(second_env["GIT_ASKPASS"])
        assert second_script != first_script or not first_script.exists()
        assert second_script.exists()
    assert not first_script.exists()
    assert not second_script.exists()
