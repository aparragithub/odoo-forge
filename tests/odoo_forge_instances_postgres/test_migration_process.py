"""Process-level import-purity and sync-only contracts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

MARKER_PACKAGES = (
    "odoo_forge_instances_postgres",
    "odoo_forge_instances_postgres.migrations",
)
MIGRATE_MODULE = "odoo_forge_instances_postgres.migrate"
RELEASE_SMOKE_SCRIPT = Path(__file__).parents[2] / "scripts/release_smoke.sh"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


def _assert_clean_exit(code: str) -> None:
    result = _run(code)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "code",
    [
        "import odoo_forge_instances_postgres as p; "
        "assert p.__all__ == ['MigrationAutocommitError', 'MigrationLockTimeoutError', "
        "'RegistryTableRejectedError', 'CatalogVerificationError']",
        "import odoo_forge_instances_postgres.migrations as p; assert p.__all__ == []",
        "import odoo_forge_instances_postgres.migrate as m; assert callable(m.run_migration)",
    ],
)
def test_imports_are_side_effect_free(code: str) -> None:
    _assert_clean_exit(code)


@pytest.mark.parametrize("marker", MARKER_PACKAGES)
def test_importing_a_marker_does_not_load_the_migration_module(marker: str) -> None:
    """Importing a marker package must leave the migration module unloaded."""

    _assert_clean_exit(
        f"import sys, {marker}; "
        f"assert {MIGRATE_MODULE!r} not in sys.modules, "
        f"'{marker} transitively imported the migration module'"
    )


def test_root_import_exports_errors_without_loading_runtime_modules() -> None:
    _assert_clean_exit(
        "import sys, odoo_forge_instances_postgres as p; "
        "assert 'odoo_forge_instances_postgres.migrate' not in sys.modules; "
        "assert 'asyncio' not in sys.modules; "
        "assert p.MigrationAutocommitError.__module__ == "
        "'odoo_forge_instances_postgres.errors'"
    )


def test_importing_the_migration_module_does_not_load_asyncio() -> None:
    """The migration path is synchronous, so no async runtime may be pulled in."""

    _assert_clean_exit(
        f"import sys, {MIGRATE_MODULE}; "
        "assert 'asyncio' not in sys.modules, 'migration module imported asyncio'"
    )


def test_public_migration_callables_are_synchronous() -> None:
    """No exported callable may be a coroutine or async-generator function."""

    _assert_clean_exit(
        f"import inspect, importlib; module = importlib.import_module({MIGRATE_MODULE!r}); "
        "asynchronous = sorted( "
        "name for name in dir(module) if not name.startswith('_') "
        "and (inspect.iscoroutinefunction(getattr(module, name)) "
        "or inspect.isasyncgenfunction(getattr(module, name))) "
        "); "
        "assert not asynchronous, f'async public callables: {asynchronous}'"
    )


def _fake_uv(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uv = fake_bin / "uv"
    uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "venv" ]]; then
    target="$2"
    mkdir -p "$target/bin"
    cat > "$target/bin/python" <<'PYTHON'
#!/usr/bin/env bash
if [[ -n "${PYTHONPATH:-}" ]]; then
    exit 42
fi
if [[ "$*" == *"time.sleep"* ]]; then
    sleep 2
fi
exit "${FAKE_PYTHON_STATUS:-0}"
PYTHON
    cat > "$target/bin/forge" <<'FORGE'
#!/usr/bin/env bash
exit "${FAKE_FORGE_STATUS:-0}"
FORGE
    chmod +x "$target/bin/python" "$target/bin/forge"
elif [[ "$1" == "pip" ]]; then
    exit "${FAKE_UV_STATUS:-0}"
else
    exit 99
fi
""",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    return fake_bin


def _run_release_smoke(
    tmp_path: Path, *, forge_status: int = 0, uv_status: int = 0
) -> subprocess.CompletedProcess[str]:
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    (wheel_dir / "odoo_forge_toolkit-0.1.1-py3-none-any.whl").touch()
    fake_bin = _fake_uv(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_FORGE_STATUS": str(forge_status),
            "FAKE_UV_STATUS": str(uv_status),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "TMPDIR": str(tmp_path),
        }
    )
    return subprocess.run(
        ["bash", str(RELEASE_SMOKE_SCRIPT), str(wheel_dir)],
        capture_output=True,
        cwd=tmp_path,
        env=environment,
        text=True,
        check=False,
    )


def test_release_smoke_script_succeeds_and_cleans_owned_workspace(tmp_path: Path) -> None:
    result = _run_release_smoke(tmp_path)

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.glob("odoo-forge-wheel-smoke.*")) == []


def test_release_smoke_script_propagates_cli_failure_and_cleans_workspace(tmp_path: Path) -> None:
    result = _run_release_smoke(tmp_path, forge_status=23)

    assert result.returncode == 23
    assert list(tmp_path.glob("odoo-forge-wheel-smoke.*")) == []
