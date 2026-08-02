"""Opt-in process availability evidence for the driver-neutral PostgreSQL harness."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from odoo_forge_instances_postgres.real_postgres import postgres_harness

pytestmark = [pytest.mark.integration, pytest.mark.real_docker]


def _require_real_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker prerequisite unavailable: executable not found")
    if os.environ.get("ODOO_FORGE_RUN_REAL_DOCKER") != "1":
        pytest.skip("real Docker smoke disabled; set ODOO_FORGE_RUN_REAL_DOCKER=1 explicitly")
    result = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Docker prerequisite unavailable: daemon is unreachable")


def test_real_postgres_process_is_explicitly_opt_in_and_available() -> None:
    _require_real_docker()
    with postgres_harness() as session:
        assert session.connection.database.startswith("odoo_")
