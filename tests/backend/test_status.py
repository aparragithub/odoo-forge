from pathlib import Path

from odoo_forge.backend.status import (
    ExecResult,
    InstanceRef,
    InstanceStatus,
    RoleStatus,
    derive_instance_ref,
    parse_status,
)
from odoo_forge.manifest.schema import Client, Manifest


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path=Path("client/addons")),
    }
    defaults.update(overrides)
    return Manifest(**defaults)  # type: ignore[arg-type]


def _container(
    *, role: str, running: bool, health_status: str | None, has_health_key: bool = True
) -> dict[str, object]:
    state: dict[str, object] = {"Running": running, "Status": "running" if running else "exited"}
    if has_health_key:
        state["Health"] = {"Status": health_status} if health_status is not None else None
    return {
        "Config": {"Labels": {"com.odoo-forge.role": role}},
        "State": state,
    }


class TestInstanceRef:
    def test_derive_instance_ref_uses_canonical_default_identity(self) -> None:
        ref = derive_instance_ref(_manifest(), "default")

        assert isinstance(ref, InstanceRef)
        assert ref == InstanceRef(
            project="odoo-idp",
            instance="default",
            network="odoo-forge-odoo-idp-default",
            postgres_container="odoo-forge-odoo-idp-default-db",
            odoo_container="odoo-forge-odoo-idp-default-odoo",
        )

    def test_derive_instance_ref_is_scan_free_and_matches_plan_identity(self) -> None:
        ref = derive_instance_ref(_manifest(), "My Inst/2")

        assert ref == InstanceRef(
            project="odoo-idp",
            instance="myinst2-b80042ab",
            network="odoo-forge-odoo-idp-myinst2-b80042ab",
            postgres_container="odoo-forge-odoo-idp-myinst2-b80042ab-db",
            odoo_container="odoo-forge-odoo-idp-myinst2-b80042ab-odoo",
        )


class TestParseStatusRunningStateFirst:
    def test_odoo_running_false_maps_to_exited_regardless_of_stale_health(self) -> None:
        containers = [
            _container(role="odoo", running=False, health_status="healthy"),
            _container(role="postgres", running=True, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.running is False
        assert status.odoo.state == "exited"

    def test_postgres_running_false_maps_to_exited_regardless_of_stale_health(self) -> None:
        containers = [
            _container(role="odoo", running=True, health_status="healthy"),
            _container(role="postgres", running=False, health_status="healthy"),
        ]

        status = parse_status(containers)

        assert status.postgres.running is False
        assert status.postgres.state == "exited"

    def test_odoo_exited_with_null_health_is_exited_not_unknown(self) -> None:
        containers = [
            _container(role="odoo", running=False, health_status=None),
            _container(role="postgres", running=False, health_status=None),
        ]

        status = parse_status(containers)

        assert status.odoo.state == "exited"


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
