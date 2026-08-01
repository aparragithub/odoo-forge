"""Process-level import-purity and sync-only contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "odoo_forge_instances_postgres"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


@pytest.mark.parametrize(
    "code",
    [
        "import odoo_forge_instances_postgres as p; assert p.__all__ == []",
        "import odoo_forge_instances_postgres.migrations as p; assert p.__all__ == []",
        "import odoo_forge_instances_postgres.migrate as m; assert callable(m.run_migration)",
    ],
)
def test_imports_are_side_effect_free(code: str) -> None:
    result = _run(code)
    assert result.returncode == 0, result.stderr


def test_markers_do_not_import_migrate() -> None:
    for path in (PACKAGE_ROOT / "__init__.py", PACKAGE_ROOT / "migrations" / "__init__.py"):
        assert "migrate" not in path.read_text(encoding="utf-8")


def test_package_is_synchronous_only() -> None:
    for path in PACKAGE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "import asyncio" not in source, f"{path} imports asyncio"
        assert "async def" not in source, f"{path} defines an async function"
