"""RED-first tests for the real Docker-backed Postgres `RestoreTarget` (PR4/D1).

Streams a `database` component's staged bytes into a provisioned container
via `docker exec ... pg_restore` (argv-only, no shell); a `filestore`
component is accepted as a no-op success (D6 pass-through seam).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
)
from odoo_forge_postgres_docker.restore_target import (
    InvalidRestoreIdentifierError,
    RestoreByteSourceUnavailableError,
    RestoreInjectionBinaryUnavailableError,
    RestoreInjectionFailedError,
    RestoreInjectionTimeoutError,
    make_docker_restore_target,
)

_DIGEST = ArtifactDigest(algorithm="sha256", value="a" * 64)


def _database_component(ref: str = "database-odoo-target") -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=ArtifactComponentKind.DATABASE,
        opaque_component_ref=ref,
        format_version="pg_dump-custom-v1",
        digest=_DIGEST,
    )


def _filestore_component() -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=ArtifactComponentKind.FILESTORE,
        opaque_component_ref="filestore-empty-v1",
        format_version="empty-v1",
        digest=ArtifactDigest(
            algorithm="sha256",
            value="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
    )


class _RecordingRunner:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self._returncode = returncode

    def __call__(
        self, argv: Sequence[str], *, stdin_path: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(argv), stdin_path))
        return subprocess.CompletedProcess(list(argv), self._returncode, "", "")


class _MissingBinaryRunner:
    def __call__(
        self, argv: Sequence[str], *, stdin_path: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker")


class _TimeoutRunner:
    def __call__(
        self, argv: Sequence[str], *, stdin_path: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(list(argv), timeout)


def _byte_source(path: Path) -> Callable[[RestoreSetComponent], Path]:
    def _resolve(_component: RestoreSetComponent) -> Path:
        return path

    return _resolve


def test_restore_target_streams_database_component_via_argv_only_pg_restore(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "database-odoo-target.dump"
    staged.write_bytes(b"dump-bytes")
    runner = _RecordingRunner()
    target = make_docker_restore_target(byte_source=_byte_source(staged), runner=runner)

    result = target(_database_component(), "odoo-target")

    assert result is True
    argv, stdin_path = runner.calls[0]
    assert argv[:4] == ["docker", "exec", "-i", "odoo-target"]
    assert "pg_restore" in argv
    assert "-d" in argv and "odoo-target" in argv
    assert stdin_path == staged
    for item in argv:
        assert isinstance(item, str)


def test_restore_target_returns_true_on_success() -> None:
    runner = _RecordingRunner(returncode=0)
    target = make_docker_restore_target(byte_source=_byte_source(Path("/dev/null")), runner=runner)

    assert target(_database_component(), "odoo-target") is True


def test_restore_target_nonzero_returncode_raises_distinct_failed_error() -> None:
    runner = _RecordingRunner(returncode=1)
    target = make_docker_restore_target(byte_source=_byte_source(Path("/dev/null")), runner=runner)

    with pytest.raises(RestoreInjectionFailedError) as exc_info:
        target(_database_component(), "odoo-target")

    assert str(exc_info.value) == RestoreInjectionFailedError.public_detail


def test_restore_target_missing_docker_binary_raises_distinct_error() -> None:
    target = make_docker_restore_target(
        byte_source=_byte_source(Path("/dev/null")), runner=_MissingBinaryRunner()
    )

    with pytest.raises(RestoreInjectionBinaryUnavailableError) as exc_info:
        target(_database_component(), "odoo-target")

    assert str(exc_info.value) == RestoreInjectionBinaryUnavailableError.public_detail


def test_restore_target_timeout_raises_distinct_timeout_error() -> None:
    target = make_docker_restore_target(
        byte_source=_byte_source(Path("/dev/null")), runner=_TimeoutRunner()
    )

    with pytest.raises(RestoreInjectionTimeoutError) as exc_info:
        target(_database_component(), "odoo-target")

    assert str(exc_info.value) == RestoreInjectionTimeoutError.public_detail


@pytest.mark.parametrize(
    "unsafe_target",
    [
        "odoo; rm -rf /",
        "odoo && echo pwned",
        "odoo$(whoami)",
        "odoo target",
        "Odoo-Target",
    ],
)
def test_restore_target_rejects_unsafe_target_identifiers_before_invoking_runner(
    unsafe_target: str,
) -> None:
    runner = _RecordingRunner()
    target = make_docker_restore_target(byte_source=_byte_source(Path("/dev/null")), runner=runner)

    with pytest.raises(InvalidRestoreIdentifierError) as exc_info:
        target(_database_component(), unsafe_target)

    assert runner.calls == []
    assert str(exc_info.value) == InvalidRestoreIdentifierError.public_detail


def test_restore_target_default_byte_source_raises_when_unconfigured() -> None:
    runner = _RecordingRunner()
    target = make_docker_restore_target(runner=runner)

    with pytest.raises(RestoreByteSourceUnavailableError):
        target(_database_component(), "odoo-target")

    assert runner.calls == []


def test_filestore_component_is_a_no_op_success_without_invoking_docker() -> None:
    runner = _RecordingRunner()
    target = make_docker_restore_target(byte_source=_byte_source(Path("/dev/null")), runner=runner)

    result = target(_filestore_component(), "odoo-target")

    assert result is True
    assert runner.calls == []


def test_default_runner_streams_from_file_argv_only_never_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = tmp_path / "database-odoo-target.dump"
    staged.write_bytes(b"dump-bytes")
    captured_kwargs: dict[str, object] = {}

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_kwargs.update(kwargs)
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    target = make_docker_restore_target(byte_source=_byte_source(staged))

    assert target(_database_component(), "odoo-target") is True
    assert captured_kwargs["shell"] is False
    assert "timeout" in captured_kwargs
    assert captured_kwargs["stdin"] is not None
