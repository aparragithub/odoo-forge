"""Sever the Docker-backed documentation renderer for this suite's default run.

``validate_repository`` calls ``validate_documentation(root)`` by module-global
name lookup at call time, so patching the ``validate`` module attribute reaches
every caller that goes through ``validate_repository``. This autouse fixture
replaces ``validate.validate_documentation`` with a thin wrapper around the
*original* function whose ``run_renderer`` default is a no-op returning
``RendererResult(0, "")`` instead of invoking ``run_fixed_renderer`` (which
shells out to the Docker-backed
``docs/diagrams/render-current-implementation.sh`` via ``subprocess.run``).
All other documentation checks performed by ``validate_documentation`` (link
resolution, ownership markers, current-target labels, etc.) still run
unmodified — only the renderer invocation is stubbed.

``run_fixed_renderer`` captures ``subprocess.run`` in its ``run_process``
default at definition time, so module-attribute patching does not replace the
function already bound there. The bound renderer default can still be replaced
explicitly through ``validate.run_fixed_renderer.__defaults__`` when a test
needs a fail-fast sentinel. Patching
``validate.validate_documentation`` at the module-attribute level remains the
supported external seam without editing the validator.

Durability note: this stub covers any future test that reaches Docker via
``validate_repository`` or ``validate_documentation``. A future test that
calls ``run_fixed_renderer`` directly with its own default argument bypasses
this stub entirely and MUST carry the existing ``real_docker`` marker
instead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import validate

_ORIGINAL_VALIDATE_DOCUMENTATION: Callable[..., list[Any]] = validate.validate_documentation


def _no_docker_run_renderer(root: Any) -> Any:
    return validate.RendererResult(0, "")


def _stub_validate_documentation(
    root: Any, run_renderer: Callable[[Any], Any] = _no_docker_run_renderer
) -> list[Any]:
    return _ORIGINAL_VALIDATE_DOCUMENTATION(root, run_renderer=run_renderer)


def _install_renderer_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validate, "validate_documentation", _stub_validate_documentation)


@pytest.fixture(autouse=True)
def _stub_docker_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_renderer_stub(monkeypatch)
