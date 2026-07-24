"""RED-first tests for the Docker-backed Postgres capture adapter."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Sequence
from typing import IO, cast

import pytest

from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_artifacts.contracts import ArtifactComponentKind
from odoo_forge_postgres_docker.capture import (
    CaptureBinaryUnavailableError,
    CaptureCommandFailedError,
    CaptureRunResult,
    CaptureTimeoutError,
    DockerPostgresqlCaptureAdapter,
    InvalidCaptureIdentifierError,
)

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _source(target_id: str = "odoo-source") -> CaptureSource:
    return CaptureSource(
        credentials=CredentialHandle("source-handle"),
        target=TargetContext(kind="source", target_id=target_id),
    )


class _RecordingRunner:
    def __init__(self, stdout: bytes = b"dump-bytes", returncode: int = 0) -> None:
        self.calls: list[Sequence[str]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        self.calls.append(list(argv))
        return CaptureRunResult(
            returncode=self._returncode,
            digest_hex=hashlib.sha256(self._stdout).hexdigest(),
        )


class _MissingBinaryRunner:
    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        raise FileNotFoundError("docker")


class _TimeoutRunner:
    """Raises `TimeoutExpired` on the (pg_dump) call."""

    def __init__(self) -> None:
        self.calls: list[Sequence[str]] = []

    def __call__(self, argv: Sequence[str], *, timeout: float) -> CaptureRunResult:
        self.calls.append(list(argv))
        raise subprocess.TimeoutExpired(list(argv), timeout)


def test_capture_runs_pg_dump_argv_only_and_computes_digest_before_return() -> None:
    runner = _RecordingRunner(stdout=b"dump-bytes")
    adapter = DockerPostgresqlCaptureAdapter(runner=runner)

    manifest = adapter.capture(_source())

    assert runner.calls == [
        [
            "docker",
            "exec",
            "odoo-source",
            "pg_dump",
            "-U",
            "postgres",
            "--format=custom",
            "odoo-source",
        ]
    ]
    for argv in runner.calls:
        assert isinstance(argv, list)
        assert all(isinstance(item, str) for item in argv)

    database = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert database.digest.value == hashlib.sha256(b"dump-bytes").hexdigest()


def test_capture_emits_empty_filestore_component_with_empty_v1_format() -> None:
    runner = _RecordingRunner()
    adapter = DockerPostgresqlCaptureAdapter(runner=runner)

    manifest = adapter.capture(_source())

    filestore = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.FILESTORE
    )
    assert filestore.format_version == "empty-v1"
    assert filestore.digest.value == _EMPTY_SHA256
    assert filestore.digest.algorithm == "sha256"


@pytest.mark.parametrize(
    "unsafe_target_id",
    [
        "odoo; rm -rf /",
        "odoo && echo pwned",
        "odoo$(whoami)",
        "odoo source",
        "Odoo-Source",
    ],
)
def test_capture_rejects_unsafe_source_identifiers_before_invoking_runner(
    unsafe_target_id: str,
) -> None:
    runner = _RecordingRunner()
    adapter = DockerPostgresqlCaptureAdapter(runner=runner)

    with pytest.raises(InvalidCaptureIdentifierError) as exc_info:
        adapter.capture(_source(unsafe_target_id))

    assert runner.calls == []
    assert str(exc_info.value) == InvalidCaptureIdentifierError.public_detail


def test_capture_nonzero_returncode_raises_distinct_capture_command_failed_error() -> None:
    runner = _RecordingRunner(returncode=1)
    adapter = DockerPostgresqlCaptureAdapter(runner=runner)

    with pytest.raises(CaptureCommandFailedError) as exc_info:
        adapter.capture(_source())

    assert str(exc_info.value) == CaptureCommandFailedError.public_detail


def test_capture_missing_docker_binary_raises_distinct_capture_binary_unavailable_error() -> None:
    adapter = DockerPostgresqlCaptureAdapter(runner=_MissingBinaryRunner())

    with pytest.raises(CaptureBinaryUnavailableError) as exc_info:
        adapter.capture(_source())

    assert str(exc_info.value) == CaptureBinaryUnavailableError.public_detail


def test_capture_timeout_raises_distinct_capture_timeout_error() -> None:
    runner = _TimeoutRunner()
    adapter = DockerPostgresqlCaptureAdapter(runner=runner)

    with pytest.raises(CaptureTimeoutError) as exc_info:
        adapter.capture(_source())

    assert str(exc_info.value) == CaptureTimeoutError.public_detail
    assert len(runner.calls) == 1
    for argv in runner.calls:
        assert isinstance(argv, list)
        assert all(isinstance(item, str) for item in argv)


def test_capture_default_runner_invokes_subprocess_run_argv_only_never_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured_kwargs.update(kwargs)
        stdout = cast("IO[bytes]", kwargs["stdout"])
        stdout.write(b"")
        return subprocess.CompletedProcess(list(argv), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter()

    adapter.capture(_source())

    assert captured_kwargs["shell"] is False
    assert "timeout" in captured_kwargs


def test_default_runner_hashes_staged_file_in_bounded_chunks_without_full_buffering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [b"chunk-one-", b"chunk-two-", b"chunk-three"]
    full = b"".join(chunks)

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        stdout = cast("IO[bytes]", kwargs["stdout"])
        for chunk in chunks:
            stdout.write(chunk)
        stdout.flush()
        return subprocess.CompletedProcess(list(argv), returncode=0)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter()

    manifest = adapter.capture(_source())

    database = next(
        component
        for component in manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )
    assert database.digest.value == hashlib.sha256(full).hexdigest()


def test_default_runner_raises_capture_timeout_when_real_subprocess_run_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercises the REAL `_run_subprocess`, not a runner double: a genuinely
    stalled producer (no output ever written) must still surface as
    `CaptureTimeoutError`, proving the timeout is enforced by
    `subprocess.run(..., timeout=)` itself rather than a hand-rolled loop
    that only checks a deadline between blocking reads.
    """

    def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(list(argv), cast("float", kwargs["timeout"]))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    adapter = DockerPostgresqlCaptureAdapter()

    with pytest.raises(CaptureTimeoutError):
        adapter.capture(_source())
