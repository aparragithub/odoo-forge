from odoo_forge.backend.plan import plan_backend
from odoo_forge.backend.status import (
    ExecResult,
    InstanceRef,
    InstanceStatus,
    RoleStatus,
    instance_ref,
    parse_status,
)
from odoo_forge.manifest.schema import Client, Manifest
from odoo_forge.manifest.state import MaterializedState


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path="client/addons"),
    }
    defaults.update(overrides)
    return Manifest(**defaults)  # type: ignore[arg-type]


def _plan():
    return plan_backend(_manifest(), MaterializedState())


def _container(*, role: str, running: bool, health_status: str | None, has_health_key: bool = True) -> dict:
    state: dict[str, object] = {"Running": running, "Status": "running" if running else "exited"}
    if has_health_key:
        state["Health"] = {"Status": health_status} if health_status is not None else None
    return {
        "Config": {"Labels": {"com.odoo-forge.role": role}},
        "State": state,
    }


class TestInstanceRef:
    def test_instance_ref_from_plan(self) -> None:
        plan = _plan()

        ref = instance_ref(plan)

        assert isinstance(ref, InstanceRef)
        assert ref.network == plan.network.name
        assert ref.postgres_container == plan.postgres.name
        assert ref.odoo_container == plan.odoo.name
        assert ref.project == plan.network.labels["com.odoo-forge.project"]
        assert ref.instance == plan.network.labels["com.odoo-forge.instance"]


class TestParseStatusRunningStateFirst:
    def test_odoo_running_false_maps_to_exited_regardless_of_stale_health(self) -> None:
        containers = [
            _container(role="odoo", running=False, health_status="healthy"),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.running is False
        assert status.odoo.state == "exited"
        assert status.odoo.state != "unknown"

    def test_postgres_running_false_maps_to_exited_regardless_of_stale_health(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="healthy"),
            _container(role="postgres", running=False, health_status="healthy"),
        ]

        status = parse_status(containers)

        assert status.postgres.running is False
        assert status.postgres.state == "exited"
        assert status.postgres.state != "unknown"

    def test_odoo_exited_with_null_health_is_exited_not_unknown(self) -> None:
        containers = [
            _container(role="odoo", running=False, health_status=None),
            _container(role="postgres", running=False, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.state == "exited"
        assert status.odoo.state != "unknown"


class TestParseStatusOdooHealthMapping:
    def test_starting_maps_to_not_ready(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="starting"),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.state == "starting"
        assert status.odoo.ready is False

    def test_unhealthy_maps_to_not_ready(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="unhealthy"),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.state == "unhealthy"
        assert status.odoo.ready is False

    def test_healthy_maps_to_ready(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="healthy"),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.state == "healthy"
        assert status.odoo.ready is True

    def test_null_health_on_running_odoo_maps_to_unknown_not_ready(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status=None),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.state == "unknown"
        assert status.odoo.ready is False


class TestParseStatusPostgresNullHealth:
    def test_postgres_null_health_running_is_no_healthcheck_not_unready_permanently(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="healthy"),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.postgres.running is True
        assert status.postgres.state == "no_healthcheck"
        assert status.postgres.state != "unknown"

    def test_postgres_absent_health_key_running_is_no_healthcheck(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="healthy"),
            _container(role="postgres", running=True, health_status=None, has_health_key=False),
        ]

        status = parse_status(containers)

        assert status.postgres.running is True
        assert status.postgres.state == "no_healthcheck"


class TestParseStatusMissingRoleInArray:
    def test_only_odoo_present_postgres_falls_through_to_exited_not_odoo_status(self) -> None:
        # `docker inspect` array with only ONE role's container present (the
        # other externally removed/never created) must not crash and must
        # not leak the present role's status onto the absent role.
        containers = [_container(role="odoo", running=True, health_status="healthy")]

        status = parse_status(containers)

        assert status.odoo.running is True
        assert status.odoo.state == "healthy"
        assert status.odoo.ready is True
        assert status.postgres.running is False
        assert status.postgres.state == "exited"
        assert status.postgres.ready is False

    def test_only_postgres_present_odoo_falls_through_to_exited_not_postgres_status(self) -> None:
        containers = [_container(role="postgres", running=True, health_status=None)]

        status = parse_status(containers)

        assert status.postgres.running is True
        assert status.postgres.state == "no_healthcheck"
        assert status.odoo.running is False
        assert status.odoo.state == "exited"


class TestParseStatusEmptyAbsentInspect:
    def test_empty_list_maps_to_not_running_for_both_roles_no_raise(self) -> None:
        status = parse_status([])

        assert status.odoo.running is False
        assert status.odoo.state == "exited"
        assert status.postgres.running is False
        assert status.postgres.state == "exited"

    def test_none_maps_to_not_running_for_both_roles_no_raise(self) -> None:
        status = parse_status(None)

        assert status.odoo.running is False
        assert status.postgres.running is False


def test_instance_status_shape_matches_design_interfaces() -> None:
    status = parse_status([])

    assert isinstance(status, InstanceStatus)
    assert isinstance(status.odoo, RoleStatus)
    assert isinstance(status.postgres, RoleStatus)


def test_exec_result_shape() -> None:
    result = ExecResult(exit_code=0, stdout="ok", stderr="")

    assert result.exit_code == 0
    assert result.stdout == "ok"
    assert result.stderr == ""
