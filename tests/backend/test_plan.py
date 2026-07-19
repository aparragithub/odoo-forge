from pathlib import Path

from odoo_forge.backend.plan import (
    BackendPlan,
    ContainerRole,
    ContainerSpec,
    NetworkSpec,
    VolumeSpec,
    plan_backend,
    sanitize_name,
)
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.manifest.projection import MountEvidence, MountPlanningView
from odoo_forge.manifest.schema import (
    BackendConfig,
    Client,
    GitLayer,
    GitRepo,
    Manifest,
    OdooBackendConfig,
)


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path=Path("client/addons")),
    }
    defaults.update(overrides)
    return Manifest(**defaults)  # type: ignore[arg-type]


def _mount_view() -> MountPlanningView:
    return MountPlanningView(
        mounts=(
            MountEvidence(
                layer="core",
                url="https://github.com/odoo/odoo.git",
                source_path=Path("/mnt/community/core/odoo"),
                container_path=Path("/mnt/community/core/odoo"),
                read_only=True,
            ),
            MountEvidence(
                layer="custom-x",
                url="https://github.com/ingadhoc/odoo-partner.git",
                source_path=Path("/mnt/worktrees/custom-x/odoo-partner"),
                container_path=Path("/mnt/custom/custom-x/odoo-partner"),
                read_only=False,
            ),
        )
    )


class TestSanitizeName:
    def test_already_valid_name_is_unchanged(self) -> None:
        assert sanitize_name("odoo-idp") == "odoo-idp"

    def test_empty_after_sanitize_falls_back_to_deterministic_slug(self) -> None:
        result = sanitize_name("!!!")

        assert result != ""
        assert result[0].isalnum()
        assert sanitize_name("!!!") == result  # deterministic

    def test_invalid_first_char_is_repaired(self) -> None:
        result = sanitize_name("-project")

        assert result[0].isalnum()
        assert sanitize_name("-project") == result  # deterministic

    def test_distinct_raw_names_sharing_a_sanitized_stem_are_distinct(self) -> None:
        first = sanitize_name("My.Project")
        second = sanitize_name("MY.PROJECT")

        assert first != second

    def test_distinct_all_invalid_names_both_empty_after_sanitize_are_distinct(self) -> None:
        # Both "!!!" and "???" sanitize to an empty stem, so both fall back to
        # the hash-of-raw slug — the raw inputs differ, so the outputs must too.
        first = sanitize_name("!!!")
        second = sanitize_name("???")

        assert first != second


class TestPlanBackend:
    def test_env_matches_entrypoint(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()

        plan = plan_backend(manifest, mount_view)

        assert set(plan.postgres.env) == {"POSTGRES_USER", "POSTGRES_DB"}
        assert set(plan.odoo.env) == {
            "DB_HOST",
            "DB_PORT",
            "DB_USER",
            "POSTGRES_DB",
            "FORGE_ADDONS_PATH_ORDER",
        }
        assert "DB_NAME" not in plan.postgres.env
        assert "DB_NAME" not in plan.odoo.env
        assert plan.odoo.env["DB_USER"] == plan.postgres.env["POSTGRES_USER"]
        assert plan.odoo.env["POSTGRES_DB"] == plan.postgres.env["POSTGRES_DB"]

    def test_odoo_env_carries_manifest_derived_addons_path_order(self) -> None:
        manifest = _manifest(
            layers=[
                GitLayer(
                    type="git",
                    name="ov",
                    category="overrides",
                    repos=[GitRepo(url="https://github.com/acme/ov.git", ref="19.0")],
                ),
                GitLayer(
                    type="git",
                    name="oca",
                    category="oca",
                    repos=[GitRepo(url="https://github.com/OCA/x.git", ref="19.0")],
                ),
            ],
            mount_priority=["custom/overrides"],
        )

        plan = plan_backend(manifest, _mount_view())

        # mount_priority entry first, then default order (system roots, then
        # remaining custom categories sorted). Consumed by entrypoint.sh.
        assert plan.odoo.env["FORGE_ADDONS_PATH_ORDER"] == (
            "/mnt/custom/overrides,/mnt/worktrees,/mnt/community,/mnt/enterprise,/mnt/custom/oca"
        )

    def test_mounts_only_validated_repositories_at_canonical_targets(self) -> None:
        plan = plan_backend(_manifest(), _mount_view())

        actual_mounts = [
            (mount.host_path, mount.container_path, mount.read_only) for mount in plan.odoo.mounts
        ]
        assert actual_mounts == [
            ("/mnt/community/core/odoo", "/mnt/community/core/odoo", True),
            ("/mnt/worktrees/custom-x/odoo-partner", "/mnt/custom/custom-x/odoo-partner", False),
        ]

    def test_image_fields_are_exact(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()

        plan = plan_backend(manifest, mount_view)

        assert plan.odoo.image == "odoo-forge-odoo:19.0"
        assert plan.postgres.image == "postgres:16"

    def test_explicit_odoo_image_override_wins_over_template(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()
        odoo_image = "ghcr.io/odoo/odoo@sha256:" + "a" * 64

        plan = plan_backend(manifest, mount_view, odoo_image=odoo_image)

        assert plan.odoo.image == odoo_image
        assert plan.postgres.image == "postgres:16"

    def test_db_host_resolves_to_postgres_alias(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()

        plan = plan_backend(manifest, mount_view)

        assert plan.odoo.env["DB_HOST"] == plan.postgres.name
        assert plan.odoo.env["DB_HOST"] != "localhost"

    def test_odoo_http_port_defaults_to_random_loopback_host_port(self) -> None:
        plan = plan_backend(_manifest(), _mount_view())

        assert plan.odoo.ports == {"8069": None, "8072": None}

    def test_odoo_http_port_can_be_fixed_from_manifest_backend_config(self) -> None:
        manifest = _manifest(backend=BackendConfig(odoo=OdooBackendConfig(http_port=18069)))

        plan = plan_backend(manifest, _mount_view())

        assert plan.odoo.ports == {"8069": 18069, "8072": None}

    def test_odoo_bind_host_defaults_to_loopback(self) -> None:
        plan = plan_backend(_manifest(), _mount_view())

        assert plan.odoo.bind_host == "127.0.0.1"
        assert plan.postgres.bind_host == "127.0.0.1"

    def test_odoo_bind_host_propagates_without_changing_port_allocation(self) -> None:
        manifest = _manifest(
            backend=BackendConfig(odoo=OdooBackendConfig(http_port=18069, bind_host="192.168.1.20"))
        )

        plan = plan_backend(manifest, _mount_view())

        assert plan.odoo.bind_host == "192.168.1.20"
        assert plan.odoo.ports == {"8069": 18069, "8072": None}

    def test_volumes_named_pg_and_filestore(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()

        plan = plan_backend(manifest, mount_view)

        assert len(plan.volumes) == 2
        assert len(plan.postgres.volumes) == 1
        assert len(plan.odoo.volumes) == 1

    def test_volume_list_consistency(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()

        plan = plan_backend(manifest, mount_view)

        referenced = {volume.name for volume in plan.postgres.volumes + plan.odoo.volumes}
        top_level = {volume.name for volume in plan.volumes}
        assert referenced == top_level

    def test_deterministic(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()
        credentials = BackendCredentialBindings(
            postgres_password=CredentialHandle("local-backend/postgres-password"),
            odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
        )

        first = plan_backend(manifest, mount_view, credentials=credentials)
        second = plan_backend(manifest, mount_view, credentials=credentials)

        assert first == second

    def test_container_role_literal_values(self) -> None:
        manifest = _manifest()
        mount_view = _mount_view()

        plan = plan_backend(manifest, mount_view)

        assert plan.postgres.role == "postgres"
        assert plan.odoo.role == "odoo"
        roles: list[ContainerRole] = ["odoo", "postgres"]
        assert plan.postgres.role in roles

    def test_instance_is_sanitized_consistently_and_deterministically(self) -> None:
        # A messy `--instance` value must sanitize through the SAME
        # `sanitize_name` as `manifest.name` in every name/label, and do so
        # identically across independent calls — `run`/`status` each build
        # their own `BackendPlan` with no shared registry, so a mismatch
        # here would mean `status` looks up the wrong container.
        manifest = _manifest()
        mount_view = _mount_view()
        messy_instance = "My Inst/2"
        expected = sanitize_name(messy_instance)

        plan = plan_backend(manifest, mount_view, instance=messy_instance)

        assert expected in plan.network.name
        assert expected in plan.postgres.name
        assert expected in plan.odoo.name
        assert plan.network.labels["com.odoo-forge.instance"] == expected
        assert " " not in plan.network.name
        assert "/" not in plan.network.name
        assert plan_backend(manifest, mount_view, instance=messy_instance) == plan


def test_backend_plan_shape_matches_design_interfaces() -> None:
    manifest = _manifest()
    mount_view = _mount_view()

    plan = plan_backend(manifest, mount_view)

    assert isinstance(plan, BackendPlan)
    assert isinstance(plan.network, NetworkSpec)
    assert all(isinstance(volume, VolumeSpec) for volume in plan.volumes)
    assert isinstance(plan.postgres, ContainerSpec)
    assert isinstance(plan.odoo, ContainerSpec)


def test_backend_plan_keeps_credential_handles_out_of_public_environment() -> None:
    credentials = BackendCredentialBindings(
        postgres_password=CredentialHandle("local-backend/postgres-password"),
        odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
    )

    plan = plan_backend(_manifest(), _mount_view(), credentials=credentials)

    assert plan.postgres.secret_env == {"POSTGRES_PASSWORD": credentials.postgres_password}
    assert plan.odoo.secret_env == {"DB_PASSWORD": credentials.odoo_db_password}


def test_backend_plan_never_places_passwords_in_public_environment() -> None:
    manifest = _manifest()
    plan = plan_backend(manifest, _mount_view())

    assert "POSTGRES_PASSWORD" not in plan.postgres.env
    assert "DB_PASSWORD" not in plan.odoo.env
