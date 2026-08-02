"""Behavior tests for the release smoke script."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

import pytest

RELEASE_SMOKE_SCRIPT = Path(__file__).parents[2] / "scripts/release_smoke.sh"


def _fake_uv(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uv = fake_bin / "uv"
    uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${FAKE_UV_SIGNAL:-}" ]]; then
    kill -s "$FAKE_UV_SIGNAL" "$PPID"
    exit 0
fi
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
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "FAKE_FORGE_STATUS": str(forge_status),
            "FAKE_UV_STATUS": str(uv_status),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
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


def test_release_smoke_script_propagates_uv_failure_and_cleans_workspace(tmp_path: Path) -> None:
    result = _run_release_smoke(tmp_path, uv_status=17)

    assert result.returncode == 17
    assert list(tmp_path.glob("odoo-forge-wheel-smoke.*")) == []


@pytest.mark.parametrize("interrupt", [signal.SIGHUP, signal.SIGINT, signal.SIGTERM])
def test_release_smoke_script_signal_cleans_and_exits_immediately(
    tmp_path: Path, interrupt: signal.Signals
) -> None:
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    (wheel_dir / "odoo_forge_toolkit-0.1.1-py3-none-any.whl").touch()
    fake_bin = _fake_uv(tmp_path)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "FAKE_UV_SIGNAL": interrupt.name,
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "TMPDIR": str(tmp_path),
        }
    )
    process = subprocess.Popen(  # noqa: S603
        ["bash", str(RELEASE_SMOKE_SCRIPT), str(wheel_dir)],
        cwd=tmp_path,
        env=environment,
        start_new_session=True,
    )
    try:
        assert process.wait(timeout=2) == 128 + interrupt
        assert list(tmp_path.glob("odoo-forge-wheel-smoke.*")) == []
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
