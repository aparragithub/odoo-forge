"""Test setup for the portfolio-verification package.

`testpaths` collects `tests/` before `docs/tools/platform_portfolio`, so
pytest's own rootdir-prepend has not yet added the latter to `sys.path` when
this package's test modules are imported. This conftest inserts it explicitly
at conftest-import time (pytest imports a directory's conftest before its
test modules), mirroring the existing collection-time side-effect precedent
in `tests/conftest.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATOR_DIR = _REPO_ROOT / "docs" / "tools" / "platform_portfolio"
if str(_VALIDATOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATOR_DIR))

_LIVE_PLAN_PATH = _REPO_ROOT / "docs" / "specs" / "platform" / "portfolio.json"


@pytest.fixture(scope="session")
def live_plan() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_LIVE_PLAN_PATH.read_text(encoding="utf-8")))
