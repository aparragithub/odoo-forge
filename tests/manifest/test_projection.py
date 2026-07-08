from collections.abc import Sequence
from pathlib import Path

import pytest

from odoo_forge.manifest.errors import ProjectionError, ScanError
from odoo_forge.manifest.lockfile import Lockfile, ResolvedLayer, ResolvedRepo
from odoo_forge.manifest.projection import (
    MOUNT_ROOTS,
    ScannedRepo,
    WorkspacePlan,
    WorkspacePlanEntry,
    classify_root,
    materialize_state,
    plan_projection,
    plan_unlock,
    project_workspace,
)
from odoo_forge.manifest.schema import (
    Client,
    CoreLayer,
    GitLayer,
    GitRepo,
    Manifest,
    PublishedLayer,
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


def _git_layer(**overrides: object) -> GitLayer:
    defaults: dict[str, object] = {
        "type": "git",
        "name": "localization",
        "repos": [GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
    }
    defaults.update(overrides)
    return GitLayer(**defaults)  # type: ignore[arg-type]


class TestClassifyRoot:
    def test_legacy_layer_without_category_falls_back_to_custom(self) -> None:
        layer = _git_layer()

        assert layer.category is None
        assert classify_root(layer) == "custom"

    def test_explicit_category_is_honored(self) -> None:
        layer = _git_layer(category="localization")

        assert classify_root(layer) == "localization"

    def test_enterprise_repo_forces_enterprise_root_regardless_of_category(self) -> None:
        layer = _git_layer(category="localization", requires_edition="enterprise")

        assert classify_root(layer) == "enterprise"

    def test_core_always_classifies_to_community(self) -> None:
        assert classify_root(CoreLayer()) == "community"

    def test_published_layer_default_category_is_custom(self) -> None:
        layer = PublishedLayer(
            type="published",
            name="enterprise",
            source="registry://example/odoo-ee",
            version="19.0.1",
        )

        assert classify_root(layer) == "custom"

    @pytest.mark.parametrize(
        "layer",
        [
            CoreLayer(),
            _git_layer(),
            _git_layer(category="community"),
            _git_layer(category="custom"),
            _git_layer(category="localization"),
            _git_layer(category="enterprise"),
            _git_layer(requires_edition="enterprise"),
        ],
    )
    def test_never_returns_worktrees(self, layer: object) -> None:
        # `classify_root` is statically typed to never return "worktrees";
        # this asserts that runtime invariant, so the comparison is
        # intentionally always-true to mypy.
        assert classify_root(layer) != "worktrees"  # type: ignore[arg-type, comparison-overlap]
        assert classify_root(layer) in MOUNT_ROOTS  # type: ignore[arg-type]


class TestPlanProjection:
    def test_plan_mirrors_lock_order(self) -> None:
        manifest = _manifest(
            edition="enterprise",
            layers=[
                _git_layer(name="custom-x", category="custom"),
                PublishedLayer(
                    type="published",
                    name="enterprise",
                    source="registry://example/odoo-ee",
                    version="19.0.1",
                    requires_edition="enterprise",
                ),
            ],
        )
        lock = Lockfile(
            generated_from="hash",
            layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="enterprise",
                    repos=[
                        ResolvedRepo(
                            url="https://github.com/acme/odoo-ee.git", ref="19.0", commit="sha-ee"
                        )
                    ],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[
                        ResolvedRepo(
                            url="https://github.com/ingadhoc/odoo-partner.git",
                            ref="19.0",
                            commit="sha-partner",
                        )
                    ],
                ),
            ],
        )

        plan = plan_projection(manifest, lock)

        assert [step.layer for step in plan.steps] == ["core", "enterprise", "custom-x"]
        assert [step.mount_root for step in plan.steps] == ["community", "enterprise", "custom"]
        assert [step.commit for step in plan.steps] == ["sha-core", "sha-ee", "sha-partner"]

    def test_orphaned_lock_layer_raises_and_returns_no_partial_plan(self) -> None:
        manifest = _manifest()
        lock = Lockfile(
            generated_from="hash",
            layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="ghost-layer",
                    repos=[
                        ResolvedRepo(
                            url="https://github.com/acme/ghost.git", ref="19.0", commit="sha-x"
                        )
                    ],
                ),
            ],
        )

        with pytest.raises(ProjectionError, match="ghost-layer"):
            plan_projection(manifest, lock)


class _FakeWorkspaceProvider:
    """In-memory `WorkspaceProvider` test double — no I/O, records calls."""

    def __init__(self) -> None:
        self.checkout_calls: list[tuple[str, str, Path]] = []

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        self.checkout_calls.append((url, commit, dest))

    def scan(self, roots: Sequence[Path]) -> list[ScannedRepo]:
        raise NotImplementedError("scan is PR-2b scope")

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError("promote is PR-2b scope")


class TestProjectWorkspace:
    def test_calls_provider_checkout_per_entry(self) -> None:
        plan = WorkspacePlan(
            steps=[
                WorkspacePlanEntry(
                    mount_root="community",
                    layer="core",
                    url="https://github.com/odoo/odoo.git",
                    commit="sha-core",
                    target_path=Path("/mnt/community/core/odoo"),
                ),
                WorkspacePlanEntry(
                    mount_root="custom",
                    layer="custom-x",
                    url="https://github.com/ingadhoc/odoo-partner.git",
                    commit="sha-partner",
                    target_path=Path("/mnt/custom/custom-x/odoo-partner"),
                ),
            ]
        )
        provider = _FakeWorkspaceProvider()

        project_workspace(plan, provider)

        assert provider.checkout_calls == [
            (
                "https://github.com/odoo/odoo.git",
                "sha-core",
                Path("/mnt/community/core/odoo"),
            ),
            (
                "https://github.com/ingadhoc/odoo-partner.git",
                "sha-partner",
                Path("/mnt/custom/custom-x/odoo-partner"),
            ),
        ]

    def test_empty_plan_calls_provider_zero_times(self) -> None:
        plan = WorkspacePlan(steps=[])
        provider = _FakeWorkspaceProvider()

        project_workspace(plan, provider)

        assert provider.checkout_calls == []


class TestMaterializeState:
    def test_layout_and_worktrees_precedence(self) -> None:
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url="https://github.com/odoo/odoo.git",
                commit="sha-core",
            ),
            ScannedRepo(
                path=Path("/mnt/custom/custom-x/odoo-partner"),
                url="https://github.com/ingadhoc/odoo-partner.git",
                commit="sha-partner",
            ),
            # Same repo also promoted to a writable worktree at a newer commit —
            # the worktrees-root entry MUST win over the read-only projection.
            ScannedRepo(
                path=Path("/mnt/worktrees/custom-x/odoo-partner"),
                url="https://github.com/ingadhoc/odoo-partner.git",
                commit="sha-partner-writable",
            ),
        ]

        state = materialize_state(scanned, MOUNT_ROOTS)

        layers_by_name = {layer.name: layer for layer in state.layers}
        assert set(layers_by_name) == {"core", "custom-x"}
        assert [repo.commit for repo in layers_by_name["core"].repos] == ["sha-core"]

        custom_x_repos = {repo.url: repo.commit for repo in layers_by_name["custom-x"].repos}
        assert custom_x_repos == {
            "https://github.com/ingadhoc/odoo-partner.git": "sha-partner-writable",
        }

    def test_missing_directory_is_not_an_error(self) -> None:
        # No scanned entry for the "custom-x" layer at all — completes fine,
        # drift detection (not this function) reports `not_materialized`.
        state = materialize_state([], MOUNT_ROOTS)

        assert state.layers == []

    def test_malformed_scanned_path_raises_scan_error_naming_the_path(self) -> None:
        bad_path = Path("/mnt/custom/odoo-partner")  # missing the <layer> segment
        scanned = [
            ScannedRepo(
                path=bad_path,
                url="https://github.com/ingadhoc/odoo-partner.git",
                commit="sha-partner",
            )
        ]

        with pytest.raises(ScanError, match=str(bad_path)):
            materialize_state(scanned, MOUNT_ROOTS)

    def test_path_outside_any_known_root_raises_scan_error(self) -> None:
        bad_path = Path("/some/other/place/repo")
        scanned = [
            ScannedRepo(
                path=bad_path,
                url="https://github.com/ingadhoc/odoo-partner.git",
                commit="sha-partner",
            )
        ]

        with pytest.raises(ScanError, match=str(bad_path)):
            materialize_state(scanned, MOUNT_ROOTS)


class TestPlanUnlock:
    def test_computes_source_dest_and_branch_for_a_custom_layer(self) -> None:
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])

        plan = plan_unlock(manifest, "custom-x", "https://github.com/ingadhoc/odoo-partner.git")

        assert plan.source == Path("/mnt/custom/custom-x/odoo-partner")
        assert plan.dest == Path("/mnt/worktrees/custom-x/odoo-partner")
        assert plan.branch == "unlock/custom-x/odoo-partner"

    def test_computes_source_for_the_core_layer(self) -> None:
        manifest = _manifest()

        plan = plan_unlock(manifest, "core", manifest.core.url)

        assert plan.source.parts[:2] == ("/", "mnt")
        assert "community" in plan.source.parts
        assert plan.dest == Path("/mnt/worktrees/core") / plan.source.name

    def test_unknown_layer_raises_projection_error(self) -> None:
        manifest = _manifest()

        with pytest.raises(ProjectionError, match="ghost-layer"):
            plan_unlock(manifest, "ghost-layer", "https://example.com/ghost.git")
