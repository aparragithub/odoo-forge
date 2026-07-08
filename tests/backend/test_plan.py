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
from odoo_forge.manifest.schema import Client, Manifest
from odoo_forge.manifest.state import MaterializedLayer, MaterializedRepo, MaterializedState


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path=Path("client/addons")),
    }
    defaults.update(overrides)
    return Manifest(**defaults)  # type: ignore[arg-type]


def _state_with_all_roots() -> MaterializedState:
    # A materialized layer per Slice-3 root; the exact per-root attribution
    # is not carried by `MaterializedState` itself — `plan_backend` mounts
    # the fixed 5-root table unconditionally (mirrors `entrypoint.sh:82`,
    # which scans all five and skips absent directories at runtime).
    return MaterializedState(
        layers=[
            MaterializedLayer(
                name="core",
                repos=[MaterializedRepo(url="https://github.com/odoo/odoo.git", commit="sha-core")],
            ),
            MaterializedLayer(
                name="custom-x",
                repos=[
                    MaterializedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git", commit="sha-partner"
                    )
                ],
            ),
        ]
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
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

        assert set(plan.postgres.env) == {"POSTGRES_PASSWORD", "POSTGRES_USER", "POSTGRES_DB"}
        assert set(plan.odoo.env) == {"DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "POSTGRES_DB"}
        assert "DB_NAME" not in plan.postgres.env
        assert "DB_NAME" not in plan.odoo.env
        assert plan.odoo.env["DB_USER"] == plan.postgres.env["POSTGRES_USER"]
        assert plan.odoo.env["DB_PASSWORD"] == plan.postgres.env["POSTGRES_PASSWORD"]
        assert plan.odoo.env["POSTGRES_DB"] == plan.postgres.env["POSTGRES_DB"]

    def test_mounts_five_roots(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

        assert len(plan.odoo.mounts) == 5
        assert {mount.root for mount in plan.odoo.mounts} == {
            "community",
            "custom",
            "localization",
            "enterprise",
            "worktrees",
        }

    def test_mounts_identical_with_an_empty_materialized_state(self) -> None:
        # The mount table is the fixed 5-root list, independent of `state`
        # (see `plan_backend` docstring) — an empty `MaterializedState` must
        # still yield the same mount table as a populated one.
        manifest = _manifest()

        populated = plan_backend(manifest, _state_with_all_roots())
        empty = plan_backend(manifest, MaterializedState())

        assert populated.odoo.mounts == empty.odoo.mounts

    def test_image_fields_are_exact(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

        assert plan.odoo.image == "odoo-forge-odoo:19.0"
        assert plan.postgres.image == "postgres:16"

    def test_db_host_resolves_to_postgres_alias(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

        assert plan.odoo.env["DB_HOST"] == plan.postgres.name
        assert plan.odoo.env["DB_HOST"] != "localhost"

    def test_volumes_named_pg_and_filestore(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

        assert len(plan.volumes) == 2
        assert len(plan.postgres.volumes) == 1
        assert len(plan.odoo.volumes) == 1

    def test_volume_list_consistency(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

        referenced = {volume.name for volume in plan.postgres.volumes + plan.odoo.volumes}
        top_level = {volume.name for volume in plan.volumes}
        assert referenced == top_level

    def test_deterministic(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        first = plan_backend(manifest, state)
        second = plan_backend(manifest, state)

        assert first == second

    def test_container_role_literal_values(self) -> None:
        manifest = _manifest()
        state = _state_with_all_roots()

        plan = plan_backend(manifest, state)

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
        state = _state_with_all_roots()
        messy_instance = "My Inst/2"
        expected = sanitize_name(messy_instance)

        plan = plan_backend(manifest, state, instance=messy_instance)

        assert expected in plan.network.name
        assert expected in plan.postgres.name
        assert expected in plan.odoo.name
        assert plan.network.labels["com.odoo-forge.instance"] == expected
        assert " " not in plan.network.name
        assert "/" not in plan.network.name
        assert plan_backend(manifest, state, instance=messy_instance) == plan


def test_backend_plan_shape_matches_design_interfaces() -> None:
    manifest = _manifest()
    state = _state_with_all_roots()

    plan = plan_backend(manifest, state)

    assert isinstance(plan, BackendPlan)
    assert isinstance(plan.network, NetworkSpec)
    assert all(isinstance(volume, VolumeSpec) for volume in plan.volumes)
    assert isinstance(plan.postgres, ContainerSpec)
    assert isinstance(plan.odoo, ContainerSpec)
