"""Focused contracts for the Docker-free CHG-00 portfolio gate."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
import validate
from docs.tools.platform_portfolio import conftest as gate_conftest

from tests.portfolio.conftest import _load_live_plan


def test_fixture_documentation_uses_stable_validator_symbols() -> None:
    documentation = inspect.getdoc(gate_conftest)

    assert documentation is not None
    for symbol in ("validate_repository", "validate_documentation", "run_fixed_renderer"):
        assert f"``{symbol}``" in documentation
    assert "validate.py:" not in documentation


def test_validate_repository_intercepts_renderer_without_docker(
    live_plan: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    renderer_results: list[tuple[int, str]] = []
    real_renderer_result = validate.RendererResult

    def record_renderer_result(returncode: int, detail: str) -> Any:
        renderer_results.append((returncode, detail))
        return real_renderer_result(returncode, detail)

    def fail_if_renderer_runs(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Docker-backed renderer was invoked")

    monkeypatch.setattr(validate, "RendererResult", record_renderer_result)
    monkeypatch.setattr(validate.run_fixed_renderer, "__defaults__", (fail_if_renderer_runs,))
    gate_conftest._install_renderer_stub(monkeypatch)

    validate.validate_repository(Path(__file__).resolve().parents[2], live_plan)

    assert renderer_results == [(0, "")]


@pytest.mark.parametrize(
    ("contents", "message_prefix"),
    [
        (None, "live_plan: missing portfolio.json"),
        ("{not-json", "live_plan: malformed portfolio.json"),
        ("[]", "live_plan: malformed portfolio.json"),
    ],
    ids=("missing", "malformed-json", "malformed-structure"),
)
def test_load_live_plan_reports_one_controlled_failure(
    tmp_path: Path, contents: str | None, message_prefix: str
) -> None:
    path = tmp_path / "portfolio.json"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")

    with pytest.raises(pytest.fail.Exception) as failure:
        _load_live_plan(path)

    assert str(failure.value).startswith(message_prefix)


def test_load_live_plan_preserves_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "portfolio.json"
    expected = {"meta": {"schema_version": "1.0.0"}, "items": [{"id": "SP-1"}]}
    path.write_text('{"meta": {"schema_version": "1.0.0"}, "items": [{"id": "SP-1"}]}')

    assert _load_live_plan(path) == expected
