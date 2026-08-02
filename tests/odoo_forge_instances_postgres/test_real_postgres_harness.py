"""Strict-TDD lifecycle contracts for the PostgreSQL harness foundation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from subprocess import CompletedProcess

import pytest

from odoo_forge_instances_postgres.real_postgres import (
    CleanupReport,
    PostgresConnectionInfo,
    PostgresHarnessError,
    PostgresSession,
    postgres_harness,
)


class ScriptedClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ScriptedRunner:
    def __init__(self, *, ready_after: int = 0) -> None:
        self.ready_after = ready_after
        self.readiness_calls = 0
        self.calls: list[tuple[tuple[str, ...], Mapping[str, str], float]] = []

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> CompletedProcess[str]:
        command = tuple(argv)
        self.calls.append((command, env, timeout))
        if command[:3] == ("docker", "exec", "--"):
            self.readiness_calls += 1
            return CompletedProcess(command, 0 if self.readiness_calls > self.ready_after else 1)
        return CompletedProcess(command, 0)


def test_public_session_contract_is_driver_neutral_and_secret_safe() -> None:
    connection = PostgresConnectionInfo(
        host="127.0.0.1", port=55432, database="db-token", user="user-token", password="secret"
    )
    session = PostgresSession(connection=connection)

    assert connection.host == "127.0.0.1"
    assert connection.port == 55432
    assert connection.database == "db-token"
    assert connection.user == "user-token"
    assert "secret" not in repr(connection)
    assert session.cleanup_report is None
    assert CleanupReport() == CleanupReport(residuals=(), retained=())
    assert str(PostgresHarnessError("bounded failure")) == "bounded failure"


def test_harness_uses_one_token_for_owned_resources_and_yields_connection_info() -> None:
    runner = ScriptedRunner()
    clock = ScriptedClock()

    with postgres_harness(
        runner=runner,
        clock=clock,
        sleep=clock.sleep,
        token_factory=lambda: "fixture-token",
        port=55432,
    ) as session:
        assert session.connection == PostgresConnectionInfo(
            host="127.0.0.1",
            port=55432,
            database="odoo_fixture-token",
            user="odoo_fixture-token",
            password=session.connection.password,
        )
        assert session.connection.password not in " ".join(runner.calls[2][0])
        owned_commands = runner.calls[:3]
        assert all("fixture-token" in " ".join(argv) for argv, _, _ in owned_commands)

    assert runner.calls[-2][0][:3] == ("docker", "rm", "--force")
    assert runner.calls[-1][0][:3] == ("docker", "network", "rm")
    assert session.cleanup_report == CleanupReport(
        residuals=(), retained=("volume:odoo-forge-pg-volume-fixture-token",)
    )


def test_readiness_succeeds_before_the_finite_deadline() -> None:
    runner = ScriptedRunner(ready_after=2)
    clock = ScriptedClock()

    with postgres_harness(
        runner=runner,
        clock=clock,
        sleep=clock.sleep,
        token_factory=lambda: "ready-token",
        startup_timeout=1.0,
        poll_interval=0.25,
    ) as session:
        assert session.connection.database == "odoo_ready-token"

    assert runner.readiness_calls == 3
    assert clock.now == pytest.approx(0.5)


def test_readiness_failure_is_bounded_and_owned_resources_are_torn_down() -> None:
    runner = ScriptedRunner(ready_after=99)
    clock = ScriptedClock()

    with (
        pytest.raises(PostgresHarnessError, match="readiness timed out"),
        postgres_harness(
            runner=runner,
            clock=clock,
            sleep=clock.sleep,
            token_factory=lambda: "timeout-token",
            startup_timeout=0.5,
            poll_interval=0.25,
        ),
    ):
        pytest.fail("the harness must not yield before readiness")

    assert clock.now == pytest.approx(0.5)
    assert runner.calls[-2][0][:3] == ("docker", "rm", "--force")
    assert runner.calls[-1][0][:3] == ("docker", "network", "rm")
    assert all("timeout-token" in " ".join(argv) for argv, _, _ in runner.calls)
