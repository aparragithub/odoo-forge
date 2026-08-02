"""Strict-TDD lifecycle contracts for the PostgreSQL harness foundation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
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
    def __init__(
        self,
        *,
        ready_after: int = 0,
        token: str = "fixture-token",
        process_running: bool = True,
        fail_commands: frozenset[str] = frozenset(),
        foreign_resources: frozenset[str] = frozenset(),
    ) -> None:
        self.ready_after = ready_after
        self.token = token
        self.process_running = process_running
        self.fail_commands = fail_commands
        self.foreign_resources = foreign_resources
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
        if command[1:2] == ("inspect",):
            resource = command[-1]
            if resource in self.foreign_resources:
                return CompletedProcess(command, 0, stdout="foreign-token\n")
            if command[2].startswith("--format={{.State.Status}}"):
                return CompletedProcess(
                    command, 0, stdout=("running\n" if self.process_running else "exited\n")
                )
            return CompletedProcess(command, 0, stdout=f"{self.token}\n")
        if command[1] in self.fail_commands or command[2:3] and command[2] in self.fail_commands:
            return CompletedProcess(command, 1, stderr="simulated failure with secret-marker")
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
    runner = ScriptedRunner(token="fixture-token")
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
        assert runner.calls[2][1]["POSTGRES_PASSWORD"] == session.connection.password
        owned_commands = runner.calls[:3]
        assert all("fixture-token" in " ".join(argv) for argv, _, _ in owned_commands)
        assert all(
            ("--label", "odoo-forge-harness-token=fixture-token")
            in tuple(zip(argv, argv[1:], strict=False))
            for argv, _, _ in owned_commands
        )

    assert any(argv[:3] == ("docker", "rm", "--force") for argv, _, _ in runner.calls)
    assert any(argv[:3] == ("docker", "network", "rm") for argv, _, _ in runner.calls)
    assert session.cleanup_report == CleanupReport(
        residuals=(), retained=("volume:odoo-forge-pg-volume-fixture-token",)
    )


def test_readiness_succeeds_before_the_finite_deadline() -> None:
    runner = ScriptedRunner(ready_after=2, token="ready-token")
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
    readiness_timeouts = [
        timeout for argv, _, timeout in runner.calls if argv[:3] == ("docker", "exec", "--")
    ]
    assert readiness_timeouts == pytest.approx([1.0, 0.75, 0.5])


def test_readiness_failure_is_bounded_and_owned_resources_are_torn_down() -> None:
    runner = ScriptedRunner(ready_after=99, token="timeout-token")
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
    assert any(argv[:3] == ("docker", "rm", "--force") for argv, _, _ in runner.calls)
    assert any(argv[:3] == ("docker", "network", "rm") for argv, _, _ in runner.calls)
    assert all("timeout-token" in " ".join(argv) for argv, _, _ in runner.calls)


def test_scope_has_exact_leaf_files_and_no_catalog_or_migration_boundary() -> None:
    root = Path(__file__).parents[2]
    owned = {
        "src/odoo_forge_instances_postgres/real_postgres.py",
        "tests/odoo_forge_instances_postgres/test_real_postgres_harness.py",
        "tests/odoo_forge_instances_postgres/test_real_postgres_process.py",
    }
    assert all((root / path).is_file() for path in owned)
    source = (root / "src/odoo_forge_instances_postgres/real_postgres.py").read_text()
    assert not any(marker in source for marker in ("C46", "catalog", "migration"))


def test_cleanup_removes_persisted_state_only_when_explicitly_approved() -> None:
    for approved, expected_volume_action in ((False, "retained"), (True, "removed")):
        token = f"retention-{approved}"
        runner = ScriptedRunner(token=token)
        clock = ScriptedClock()

        def make_token(value: str = token) -> str:
            return value

        with postgres_harness(
            runner=runner,
            clock=clock,
            sleep=clock.sleep,
            token_factory=make_token,
            remove_persisted_state=approved,
        ) as session:
            pass

        assert session is not None
        volume = f"odoo-forge-pg-volume-{token}"
        volume_commands = [argv for argv, _, _ in runner.calls if volume in argv]
        if expected_volume_action == "retained":
            assert session.cleanup_report == CleanupReport(retained=(f"volume:{volume}",))
            assert not any(argv[1:3] == ("volume", "rm") for argv in volume_commands)
        else:
            assert session.cleanup_report == CleanupReport()
            assert any(argv[1:3] == ("volume", "rm") for argv in volume_commands)
        actions = [
            argv[1:3]
            for argv, _, _ in runner.calls
            if argv[1:3] in (("rm", "--force"), ("network", "rm"), ("volume", "rm"))
        ]
        assert actions == [("rm", "--force"), ("network", "rm")] + (
            [("volume", "rm")] if approved else []
        )


def test_cleanup_refuses_foreign_resources_and_continues_after_residuals() -> None:
    runner = ScriptedRunner(
        token="ownership-token",
        fail_commands=frozenset({"rm"}),
        foreign_resources=frozenset({"odoo-forge-pg-network-ownership-token"}),
    )

    with (
        pytest.raises(PostgresHarnessError, match="cleanup incomplete"),
        postgres_harness(
            runner=runner,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "ownership-token",
            remove_persisted_state=True,
        ) as session,
    ):
        pass

    assert session is not None
    assert session.cleanup_report == CleanupReport(
        residuals=(
            "container:remove-failed:1",
            "network:ownership-mismatch",
            "volume:remove-failed:1",
        )
    )
    assert not any(argv[1:3] == ("network", "rm") for argv, _, _ in runner.calls)
    assert any(argv[1:3] == ("volume", "rm") for argv, _, _ in runner.calls)


def test_body_exception_identity_is_preserved_and_gets_sanitized_cleanup_note() -> None:
    runner = ScriptedRunner(token="body-token", fail_commands=frozenset({"rm"}))
    error = RuntimeError("body-secret-marker")

    with (
        pytest.raises(RuntimeError) as raised,
        postgres_harness(
            runner=runner,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "body-token",
        ) as session,
    ):
        raise error

    assert raised.value is error
    assert error.__notes__ == [
        "postgres harness cleanup residuals: container:remove-failed:1, network:remove-failed:1"
    ]
    assert "body-secret-marker" not in str(error.__notes__)
    assert session is not None
    assert session.cleanup_report == CleanupReport(
        residuals=("container:remove-failed:1", "network:remove-failed:1"),
        retained=("volume:odoo-forge-pg-volume-body-token",),
    )


def test_readiness_runner_failure_is_bounded_and_secret_safe() -> None:
    secret = "readiness-secret-marker"

    def runner(
        argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> CompletedProcess[str]:
        if tuple(argv[:3]) == ("docker", "exec", "--"):
            raise OSError(f"daemon failure: {secret}")
        return CompletedProcess(list(argv), 0, stdout="fixture-token\n")

    with (
        pytest.raises(PostgresHarnessError) as raised,
        postgres_harness(
            runner=runner,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "fixture-token",
        ),
    ):
        pytest.fail("runner failure must not yield")
    assert secret not in str(raised.value)


def test_concurrent_tokens_cannot_cross_cleanup_boundaries() -> None:
    first = ScriptedRunner(token="first-token")
    second = ScriptedRunner(token="second-token")

    with (
        postgres_harness(
            runner=first,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "first-token",
        ),
        postgres_harness(
            runner=second,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "second-token",
        ),
    ):
        pass

    assert all("second-token" not in " ".join(argv) for argv, _, _ in first.calls)
    assert all("first-token" not in " ".join(argv) for argv, _, _ in second.calls)


def test_startup_failure_and_premature_exit_are_bounded_and_cleaned() -> None:
    failed_runner = ScriptedRunner(token="startup-token", fail_commands=frozenset({"run"}))
    with (
        pytest.raises(PostgresHarnessError, match="exit code 1") as raised,
        postgres_harness(
            runner=failed_runner,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "startup-token",
        ),
    ):
        pytest.fail("startup failure must not yield")
    assert "secret-marker" not in str(raised.value)
    assert any(argv[1:3] == ("network", "rm") for argv, _, _ in failed_runner.calls)
    assert any("odoo-forge-pg-volume-startup-token" in argv for argv, _, _ in failed_runner.calls)

    exited_runner = ScriptedRunner(ready_after=99, token="exited-token", process_running=False)
    with (
        pytest.raises(PostgresHarnessError, match="exited before readiness"),
        postgres_harness(
            runner=exited_runner,
            clock=ScriptedClock(),
            sleep=lambda _: None,
            token_factory=lambda: "exited-token",
        ),
    ):
        pytest.fail("premature exit must not yield")


def test_readiness_runner_timeout_cannot_overrun_deadline() -> None:
    clock = ScriptedClock()
    readiness_timeouts: list[float] = []

    def runner(
        argv: Sequence[str], *, env: Mapping[str, str], timeout: float
    ) -> CompletedProcess[str]:
        command = tuple(argv)
        if command[:3] == ("docker", "exec", "--"):
            readiness_timeouts.append(timeout)
            clock.now += timeout
            return CompletedProcess(command, 1)
        return CompletedProcess(command, 0)

    with (
        pytest.raises(PostgresHarnessError, match="readiness timed out"),
        postgres_harness(
            runner=runner,
            clock=clock,
            sleep=clock.sleep,
            token_factory=lambda: "deadline-token",
            startup_timeout=0.5,
            poll_interval=0.25,
        ),
    ):
        pytest.fail("the harness must not yield before readiness")

    assert readiness_timeouts == pytest.approx([0.5])
    assert clock.now == pytest.approx(0.5)
