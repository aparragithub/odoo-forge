"""Import-boundary contract coverage for `[tool.importlinter]`.

Pins the requirement that `odoo_forge` (pure core) never imports any
adapter package, including the isolated `odoo_forge_postgres_docker`
database adapter, and that `lint-imports` actually enforces it.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _contracts() -> list[dict[str, object]]:
    data = tomllib.loads(_PYPROJECT.read_text())
    return data["tool"]["importlinter"]["contracts"]


def test_forbidden_import_contract_for_postgres_docker_adapter_is_declared() -> None:
    matching = [
        contract
        for contract in _contracts()
        if contract.get("source_modules") == ["odoo_forge"]
        and contract.get("forbidden_modules") == ["odoo_forge_postgres_docker"]
    ]

    assert matching, (
        "expected a forbidden-import contract with source_modules=['odoo_forge'] "
        "and forbidden_modules=['odoo_forge_postgres_docker'] in [tool.importlinter]"
    )
    assert matching[0]["type"] == "forbidden"


def _lint_imports_command() -> list[str]:
    # Use the project's sanctioned invocation (mirrors CI: `uv run lint-imports`)
    # rather than guessing the console-script path from sys.executable, which is
    # fragile across split-bin/venv or Windows layouts.
    return ["uv", "run", "lint-imports", "--config", str(_PYPROJECT)]


def test_lint_imports_passes_with_the_postgres_docker_adapter_contract() -> None:
    result = subprocess.run(
        _lint_imports_command(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Core never imports the postgres-docker adapter" in result.stdout
