"""Context-managed real PostgreSQL resources for C46 acceptance tests."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest

from odoo_forge_instances_postgres.adapter import PostgresInstanceRegistry
from odoo_forge_instances_postgres.real_postgres import (
    CleanupReport,
    PostgresConnectionInfo,
    PostgresHarnessError,
    PostgresSession,
    postgres_harness,
)


def require_real_docker() -> None:
    """Skip only when the explicitly requested live prerequisites are absent."""
    if os.environ.get("ODOO_FORGE_RUN_REAL_DOCKER") != "1":
        pytest.skip("real Docker acceptance disabled; set ODOO_FORGE_RUN_REAL_DOCKER=1")
    if shutil.which("docker") is None:
        pytest.skip("Docker prerequisite unavailable: executable not found")
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("Docker prerequisite unavailable: daemon probe timed out after 5s")
    else:
        if result.returncode != 0:
            pytest.skip("Docker prerequisite unavailable: daemon is unreachable")


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_database(database: PostgresTestDatabase, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with database.connect() as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PostgresHarnessError("postgres database readiness timed out") from None
            time.sleep(min(0.1, remaining))


@dataclass
class PostgresTestDatabase:
    session: PostgresSession

    @property
    def info(self) -> PostgresConnectionInfo:
        return self.session.connection

    @contextmanager
    def connect(self) -> Iterator[Any]:
        with psycopg.connect(
            host=self.info.host,
            port=self.info.port,
            dbname=self.info.database,
            user=self.info.user,
            password=self.info.password,
            autocommit=False,
        ) as connection:
            yield connection

    def acquire(self) -> AbstractContextManager[Any]:
        return self.connect()

    @property
    def registry(self) -> PostgresInstanceRegistry:
        return PostgresInstanceRegistry(self.acquire)

    @property
    def cleanup_report(self) -> CleanupReport | None:
        return self.session.cleanup_report

    @property
    def clean(self) -> bool:
        report = self.cleanup_report
        return report is not None and not report.residuals and not report.retained


@contextmanager
def isolated_database() -> Iterator[PostgresTestDatabase]:
    require_real_docker()
    database: PostgresTestDatabase | None = None
    try:
        with postgres_harness(port=_free_tcp_port(), remove_persisted_state=True) as session:
            database = PostgresTestDatabase(session)
            _wait_for_database(database)
            yield database
    finally:
        if database is not None and not database.clean:
            error = sys.exception()
            detail = f"C46 cleanup residuals: {database.cleanup_report}"
            if error is None:
                raise PostgresHarnessError(detail)
            error.add_note(detail)
