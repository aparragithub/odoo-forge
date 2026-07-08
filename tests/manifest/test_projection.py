from pathlib import Path

import pytest

from odoo_forge.manifest.errors import ProjectionError
from odoo_forge.manifest.lockfile import Lockfile, ResolvedLayer, ResolvedRepo
from odoo_forge.manifest.projection import (
    MOUNT_ROOTS,
    WorkspacePlan,
    WorkspacePlanEntry,
    classify_root,
    plan_projection,
    project_workspace,
)
from odoo_forge.manifest.schema import Client, CoreLayer, GitLayer, GitRepo, Manifest, PublishedLayer


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path="client/addons"),
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
        assert classify_root(layer) != "worktrees"  # type: ignore[arg-type]
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
                        ResolvedRepo(url="https://github.com/acme/ghost.git", ref="19.0", commit="sha-x")
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

    def scan(self, roots: object) -> list[object]:
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
