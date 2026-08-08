import pytest
from typer.testing import CliRunner

from odoo_forge.pipeline.types import (
    PipelineRunRef,
    PipelineRunSpec,
    PipelineRunState,
    PipelineRunStatus,
)
from odoo_forge_cli import _composition
from odoo_forge_cli.main import app

runner = CliRunner()

_TOKEN_VALUE = "secret-token-value-should-never-leak"


class _FakePipelineProvider:
    def __init__(
        self,
        *,
        run_id: str = "12345",
        state: PipelineRunState = "succeeded",
        logs_output: str = "",
        trigger_error: Exception | None = None,
        status_error: Exception | None = None,
        logs_error: Exception | None = None,
    ) -> None:
        self.trigger_calls: list[PipelineRunSpec] = []
        self.status_calls: list[PipelineRunRef] = []
        self.logs_calls: list[PipelineRunRef] = []
        self._run_id = run_id
        self._state = state
        self._logs_output = logs_output
        self._trigger_error = trigger_error
        self._status_error = status_error
        self._logs_error = logs_error

    def trigger(self, spec: PipelineRunSpec) -> PipelineRunRef:
        self.trigger_calls.append(spec)
        if self._trigger_error is not None:
            raise self._trigger_error
        return PipelineRunRef(run_id=self._run_id)

    def status(self, ref: PipelineRunRef) -> PipelineRunStatus:
        self.status_calls.append(ref)
        if self._status_error is not None:
            raise self._status_error
        return PipelineRunStatus(state=self._state)

    def logs(self, ref: PipelineRunRef) -> str:
        self.logs_calls.append(ref)
        if self._logs_error is not None:
            raise self._logs_error
        return self._logs_output


def test_pipeline_trigger_prints_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakePipelineProvider(run_id="777")
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(app, ["pipeline-trigger", "--workflow", "ci.yml"])

    assert result.exit_code == 0
    assert result.output.strip() == "777"
    assert len(fake_provider.trigger_calls) == 1
    assert fake_provider.trigger_calls[0].definition == "ci.yml"
    assert fake_provider.trigger_calls[0].parameters == {}


def test_pipeline_trigger_maps_repeatable_params_into_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakePipelineProvider(run_id="888")
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        [
            "pipeline-trigger",
            "--workflow",
            "ci.yml",
            "--param",
            "ENV=staging",
            "--param",
            "REGION=eu",
        ],
    )

    assert result.exit_code == 0
    assert len(fake_provider.trigger_calls) == 1
    assert fake_provider.trigger_calls[0].parameters == {"ENV": "staging", "REGION": "eu"}


def test_pipeline_trigger_rejects_malformed_param_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakePipelineProvider()
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(
        app,
        ["pipeline-trigger", "--workflow", "ci.yml", "--param", "NOEQUALSSIGN"],
    )

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert fake_provider.trigger_calls == []


def test_pipeline_status_prints_run_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakePipelineProvider(state="running")
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(app, ["pipeline-status", "--run-id", "42"])

    assert result.exit_code == 0
    assert result.output.strip() == "running"
    assert len(fake_provider.status_calls) == 1
    assert fake_provider.status_calls[0].run_id == "42"


def test_pipeline_logs_forwards_run_id_and_preserves_multiline_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_text = "build started\nbuild passed"
    fake_provider = _FakePipelineProvider(logs_output=log_text)
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(app, ["pipeline-logs", "--run-id", "run-123"])

    assert result.exit_code == 0
    assert result.output == f"{log_text}\n"
    assert len(fake_provider.logs_calls) == 1
    assert fake_provider.logs_calls[0].run_id == "run-123"


def test_pipeline_logs_preserves_empty_provider_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakePipelineProvider(logs_output="")
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(app, ["pipeline-logs", "--run-id", "run-123"])

    assert result.exit_code == 0
    assert result.output == "\n"
    assert len(fake_provider.logs_calls) == 1


@pytest.mark.parametrize(
    ("command", "args", "error"),
    [
        (
            "pipeline-trigger",
            ["--workflow", "ci.yml"],
            RuntimeError("no runs found for workflow"),
        ),
        (
            "pipeline-trigger",
            ["--workflow", "ci.yml"],
            OSError("connection reset"),
        ),
        (
            "pipeline-status",
            ["--run-id", "42"],
            RuntimeError("no runs found for workflow"),
        ),
        (
            "pipeline-status",
            ["--run-id", "42"],
            OSError("connection reset"),
        ),
        (
            "pipeline-trigger",
            ["--workflow", "ci.yml"],
            KeyError("status"),
        ),
        (
            "pipeline-status",
            ["--run-id", "42"],
            KeyError("status"),
        ),
        (
            "pipeline-logs",
            ["--run-id", "42"],
            RuntimeError("logs unavailable"),
        ),
        (
            "pipeline-logs",
            ["--run-id", "42"],
            OSError("connection reset"),
        ),
        (
            "pipeline-logs",
            ["--run-id", "42"],
            KeyError("logs"),
        ),
    ],
)
def test_pipeline_commands_render_single_error_line_no_traceback(
    command: str,
    args: list[str],
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakePipelineProvider(
        trigger_error=error if command == "pipeline-trigger" else None,
        status_error=error if command == "pipeline-status" else None,
        logs_error=error if command == "pipeline-logs" else None,
    )
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(app, [command, *args])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("pipeline-trigger", ["--workflow", "ci.yml"]),
        ("pipeline-status", ["--run-id", "42"]),
        ("pipeline-logs", ["--run-id", "42"]),
    ],
)
def test_pipeline_commands_never_echo_token(
    command: str, args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORGE_PIPELINE_GITHUB_TOKEN", _TOKEN_VALUE)
    fake_provider = _FakePipelineProvider()
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: fake_provider)

    result = runner.invoke(app, [command, *args])

    assert _TOKEN_VALUE not in result.output

    error_provider = _FakePipelineProvider(
        trigger_error=RuntimeError("boom") if command == "pipeline-trigger" else None,
        status_error=RuntimeError("boom") if command == "pipeline-status" else None,
        logs_error=RuntimeError("boom") if command == "pipeline-logs" else None,
    )
    monkeypatch.setattr(_composition, "_make_pipeline_provider", lambda: error_provider)

    error_result = runner.invoke(app, [command, *args])

    assert _TOKEN_VALUE not in error_result.output


def test_pipeline_commands_reachable_from_root_app() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "pipeline-trigger" in result.output
    assert "pipeline-status" in result.output
    assert "pipeline-logs" in result.output


def test_pipeline_logs_requires_run_id_before_provider_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_composition_calls: list[None] = []

    def compose_provider() -> _FakePipelineProvider:
        provider_composition_calls.append(None)
        raise AssertionError("provider composition must not run")

    monkeypatch.setattr(_composition, "_make_pipeline_provider", compose_provider)

    result = runner.invoke(app, ["pipeline-logs"])

    assert result.exit_code == 2
    assert "--run-id" in result.output
    assert provider_composition_calls == []
