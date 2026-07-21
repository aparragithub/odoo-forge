from collections.abc import Sequence
from pathlib import Path

import pytest

from odoo_forge.manifest import projection
from odoo_forge.manifest.errors import MountPlanningError, ProjectionError, ScanError
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedPublishedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import (
    MOUNT_ROOTS,
    MountPlanningView,
    ScannedRepo,
    WorkspacePlan,
    WorkspacePlanEntry,
    build_mount_planning_view,
    build_mount_roots,
    classify_root,
    materialize_state,
    plan_projection,
    plan_unlock,
    project_workspace,
)
from odoo_forge.manifest.schema import (
    Client,
    CoreLayer,
    EnterpriseLayer,
    GitLayer,
    GitRepo,
    Manifest,
    PublishedLayer,
)
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


def _git_layer(**overrides: object) -> GitLayer:
    defaults: dict[str, object] = {
        "type": "git",
        "name": "custom-x",
        "repos": [GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
    }
    defaults.update(overrides)
    return GitLayer(**defaults)  # type: ignore[arg-type]


def _container_roots(manifest: Manifest) -> dict[str, Path]:
    """Manifest-derived container mount table (`/mnt/...` with per-category
    `custom/<category>` keys) — the pure-mount-model replacement for the bare
    `MOUNT_ROOTS` wherever a test drives `materialize_state` /
    `build_mount_planning_view` through `classify_root` (which now returns
    `custom/<category>` keys rather than a flat category root)."""
    return build_mount_roots(projection.CONTAINER_MOUNT_BASE, manifest)


class TestBuildMountRoots:
    def test_maps_the_system_roots_and_the_bare_custom_parent_without_a_manifest(self) -> None:
        base = Path("/custom/state/odoo-forge")

        roots = build_mount_roots(base)

        assert roots == {
            "community": base / "community",
            "enterprise": base / "enterprise",
            "worktrees": base / "worktrees",
            "custom": base / "custom",
        }

    def test_manifest_derived_roots_replace_bare_custom_with_per_category_keys(self) -> None:
        base = Path("/custom/state/odoo-forge")
        manifest = _manifest(
            layers=[
                _git_layer(name="partners", category="partners"),
                _git_layer(name="uncategorized"),
            ]
        )

        roots = build_mount_roots(base, manifest)

        assert roots == {
            "community": base / "community",
            "enterprise": base / "enterprise",
            "worktrees": base / "worktrees",
            "custom/partners": base / "custom" / "partners",
            "custom/default": base / "custom" / "default",
        }

    def test_explicit_custom_category_also_maps_to_the_default_folder(self) -> None:
        base = Path("/custom/state/odoo-forge")
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])

        roots = build_mount_roots(base, manifest)

        assert roots["custom/default"] == base / "custom" / "default"
        assert "custom/custom" not in roots


class TestClassifyRoot:
    def test_legacy_layer_without_category_falls_back_to_custom_default(self) -> None:
        layer = _git_layer()

        assert layer.category == "custom"
        assert classify_root(layer) == "custom/default"

    def test_explicit_category_nests_under_custom(self) -> None:
        layer = _git_layer(category="partners")

        assert classify_root(layer) == "custom/partners"

    def test_requires_enterprise_does_not_affect_mount_classification(self) -> None:
        # `requires_enterprise` is a coherence precondition only (Slice 1);
        # it must NOT influence mount classification anymore.
        layer = _git_layer(category="partners", requires_enterprise=True)

        assert classify_root(layer) == "custom/partners"

    def test_core_always_classifies_to_community(self) -> None:
        assert classify_root(CoreLayer()) == "community"

    def test_enterprise_singleton_classifies_to_enterprise(self) -> None:
        enterprise = EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0")

        assert classify_root(enterprise) == "enterprise"

    def test_published_layer_default_category_is_custom_default(self) -> None:
        layer = PublishedLayer(
            type="published",
            name="enterprise",
            source="registry://example/odoo-ee",
            version="19.0.1",
        )

        assert classify_root(layer) == "custom/default"

    @pytest.mark.parametrize(
        ("category", "expected_root"),
        [
            ("community", "custom/community"),
            ("custom", "custom/default"),
            ("localization", "custom/localization"),
            ("enterprise", "custom/enterprise"),
            ("worktrees", "custom/worktrees"),
        ],
    )
    def test_a_category_matching_a_system_root_name_is_never_the_system_root(
        self, category: str, expected_root: str
    ) -> None:
        # Pure mount model: user layers can NEVER target a system root, even
        # when `category` is literally a reserved-looking name — it is just
        # a plain subfolder under `/mnt/custom/`.
        layer = _git_layer(category=category)

        assert classify_root(layer) == expected_root
        assert classify_root(layer) not in {"community", "enterprise", "worktrees"}

    @pytest.mark.parametrize(
        "layer",
        [
            CoreLayer(),
            EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0"),
            _git_layer(),
            _git_layer(category="community"),
            _git_layer(category="custom"),
            _git_layer(category="localization"),
            _git_layer(category="enterprise"),
            _git_layer(requires_enterprise=True),
        ],
    )
    def test_never_returns_worktrees(
        self, layer: CoreLayer | EnterpriseLayer | GitLayer | PublishedLayer
    ) -> None:
        # `classify_root` is statically typed to never return "worktrees";
        # this asserts that runtime invariant, so the comparison is
        # intentionally always-true to mypy.
        assert classify_root(layer) != "worktrees"


class TestPlanProjection:
    def test_v2_published_layers_are_retained_but_not_projected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manifest = _manifest(
            edition="enterprise",
            enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0"),
            layers=[
                PublishedLayer(
                    type="published",
                    name="enterprise-addons",
                    source="registry://example/odoo-ee",
                    version="19.0.1",
                    requires_enterprise=True,
                ),
            ],
        )
        lock = Lockfile(
            generated_from="hash",
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
            ],
            published_layers=[
                ResolvedPublishedLayer(
                    name="enterprise",
                    source="registry://example/odoo-ee",
                    version="19.0.1",
                    digest="sha256:" + "a" * 64,
                ),
            ],
        )

        monkeypatch.setattr(
            Lockfile,
            "layers",
            property(lambda _: (_ for _ in ()).throw(AssertionError("legacy layers view used"))),
        )

        plan = plan_projection(manifest, lock)

        assert [(step.layer, step.commit) for step in plan.steps] == [("core", "sha-core")]

    def test_plan_mirrors_lock_order(self) -> None:
        manifest = _manifest(
            edition="enterprise",
            enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0"),
            layers=[
                _git_layer(name="custom-x", category="custom"),
                PublishedLayer(
                    type="published",
                    name="enterprise",
                    source="registry://example/odoo-ee",
                    version="19.0.1",
                    category="enterprise",
                    requires_enterprise=True,
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
        assert [step.mount_root for step in plan.steps] == [
            "community",
            "custom/enterprise",
            "custom/default",
        ]
        assert [step.commit for step in plan.steps] == ["sha-core", "sha-ee", "sha-partner"]

    def test_honors_injected_roots_for_a_non_default_base(self) -> None:
        base = Path("/custom/state/odoo-forge")
        roots = build_mount_roots(base)
        manifest = _manifest()
        lock = Lockfile(
            generated_from="hash",
            layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
            ],
        )

        plan = plan_projection(manifest, lock, roots)

        assert plan.steps[0].target_path == roots["community"] / "core" / "odoo"

    def test_routes_a_resolved_enterprise_singleton_layer_to_its_mount(self) -> None:
        manifest = _manifest(
            edition="enterprise",
            enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0"),
        )
        lock = Lockfile(
            generated_from="hash",
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="enterprise",
                    repos=[
                        ResolvedRepo(
                            url="https://github.com/odoo/enterprise.git",
                            ref="19.0",
                            commit="sha-ee",
                        )
                    ],
                ),
            ],
        )

        plan = plan_projection(manifest, lock)

        assert [step.layer for step in plan.steps] == ["core", "enterprise"]
        assert [step.mount_root for step in plan.steps] == ["community", "enterprise"]
        assert [step.commit for step in plan.steps] == ["sha-core", "sha-ee"]

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


class TestBuildMountPlanningView:
    def test_rejects_a_lock_missing_a_manifest_required_repo(self) -> None:
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                )
            ],
        )
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            )
        ]

        with pytest.raises(MountPlanningError, match="manifest/lock structural mismatch"):
            build_mount_planning_view(
                manifest, lock, scanned, materialize_state(scanned, MOUNT_ROOTS), MOUNT_ROOTS
            )

    @pytest.mark.parametrize(
        ("url", "expected", "secrets"),
        [
            (
                "https://username:password@example.com/org/repo.git",
                "repo",
                ("username", "password"),
            ),
            (
                "https://username:password@example.com",
                "example.com",
                ("username", "password"),
            ),
            (
                "https://example.com/org/repo.git?token=query-secret",
                "repo",
                ("token", "query-secret"),
            ),
            (
                "https://example.com/org/repo.git#token=fragment-secret",
                "repo",
                ("token", "fragment-secret"),
            ),
            ("ssh://git@example.com/org/repo.git", "repo", ("git@",)),
            ("git@example.com:org/repo.git", "repo", ("git@", "example.com")),
            ("https://example.com/org/repo.git", "repo", ("https://", "example.com")),
            ("unrestricted-repo.git", "unrestricted-repo", ()),
            ("https://username:password@[malformed", "repository", ("username", "password")),
        ],
    )
    def test_repo_name_is_credential_safe(
        self, url: str, expected: str, secrets: tuple[str, ...]
    ) -> None:
        result = projection._repo_name(url)

        assert result == expected
        assert all(secret not in result for secret in secrets)

    @pytest.mark.parametrize(
        "custom_url",
        [
            "https://username:token@github.com/ingadhoc/odoo-partner.git?secret=query-token",
            "https://username:token@github.com/ingadhoc/odoo-partner.git#secret=fragment-token",
        ],
    )
    def test_rejects_incoherent_credential_bearing_path_without_leaking_url(
        self, custom_url: str
    ) -> None:
        manifest = _manifest(
            layers=[
                _git_layer(
                    name="custom-x",
                    category="custom",
                    repos=[GitRepo(url=custom_url, ref="19.0")],
                )
            ]
        )
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[ResolvedRepo(url=custom_url, ref="19.0", commit="sha-partner")],
                ),
            ],
        )
        roots = _container_roots(manifest)
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            ),
            ScannedRepo(
                path=Path("/mnt/custom/default/custom-x/not-odoo-partner"),
                url=custom_url,
                commit="sha-partner",
            ),
        ]

        with pytest.raises(MountPlanningError, match="custom-x") as error:
            build_mount_planning_view(
                manifest, lock, scanned, materialize_state(scanned, roots), roots
            )

        assert "odoo-partner" in str(error.value)
        assert "username" not in str(error.value)
        assert "token" not in str(error.value)
        assert "secret" not in str(error.value)
        assert "query" not in str(error.value)
        assert "fragment" not in str(error.value)
        assert "https://" not in str(error.value)
        assert custom_url not in str(error.value)

    def test_rejects_lock_drift_and_unexpected_evidence(self) -> None:
        credential_url = "https://username:token@github.com/ingadhoc/odoo-partner.git"
        unexpected_url = "https://username:token@example.com/unexpected.git"
        manifest = _manifest(
            layers=[_git_layer(name="custom-x", repos=[GitRepo(url=credential_url, ref="19.0")])]
        )
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[ResolvedRepo(url=credential_url, ref="19.0", commit="sha-partner")],
                ),
            ],
        )
        roots = _container_roots(manifest)
        drifted = [
            ScannedRepo(
                path=Path("/mnt/custom/default/custom-x/odoo-partner"),
                url=credential_url,
                commit="stale-partner",
            )
        ]
        unexpected = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            ),
            ScannedRepo(
                path=Path("/mnt/custom/default/ghost/unexpected"),
                url=unexpected_url,
                commit="sha-ghost",
            ),
        ]

        with pytest.raises(MountPlanningError, match="commit") as drift_error:
            build_mount_planning_view(
                manifest, lock, drifted, materialize_state(drifted, roots), roots
            )
        with pytest.raises(MountPlanningError, match="unexpected") as unexpected_error:
            build_mount_planning_view(
                manifest,
                lock,
                unexpected,
                materialize_state(unexpected, roots),
                roots,
            )

        for error, repo_name, repo_url in (
            (drift_error, "odoo-partner", credential_url),
            (unexpected_error, "unexpected", unexpected_url),
        ):
            assert repo_name in str(error.value)
            assert "username" not in str(error.value)
            assert "token" not in str(error.value)
            assert repo_url not in str(error.value)

    @pytest.mark.parametrize("source_root", ["custom/default", "worktrees"])
    def test_rejects_duplicate_scanned_evidence_without_leaking_url(self, source_root: str) -> None:
        credential_url = "https://username:token@github.com/ingadhoc/odoo-partner.git"
        manifest = _manifest(
            layers=[_git_layer(name="custom-x", repos=[GitRepo(url=credential_url, ref="19.0")])]
        )
        roots = _container_roots(manifest)
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[ResolvedRepo(url=credential_url, ref="19.0", commit="sha-partner")],
                ),
            ],
        )
        duplicate = ScannedRepo(
            path=roots[source_root] / "custom-x" / "odoo-partner",
            url=credential_url,
            commit="sha-partner",
        )
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            ),
            duplicate,
            duplicate,
        ]

        with pytest.raises(MountPlanningError, match="duplicate") as error:
            build_mount_planning_view(
                manifest, lock, scanned, materialize_state(scanned, roots), roots
            )

        assert "odoo-partner" in str(error.value)
        assert "username" not in str(error.value)
        assert "token" not in str(error.value)
        assert credential_url not in str(error.value)

    def test_rejects_duplicate_materialized_evidence_without_leaking_url(self) -> None:
        credential_url = "https://username:token@github.com/ingadhoc/odoo-partner.git"
        manifest = _manifest(
            layers=[_git_layer(name="custom-x", repos=[GitRepo(url=credential_url, ref="19.0")])]
        )
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[ResolvedRepo(url=credential_url, ref="19.0", commit="sha-partner")],
                ),
            ],
        )
        roots = _container_roots(manifest)
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            ),
            ScannedRepo(
                path=Path("/mnt/custom/default/custom-x/odoo-partner"),
                url=credential_url,
                commit="sha-partner",
            ),
        ]
        state = materialize_state(scanned, roots)
        state.layers[1].repos.append(state.layers[1].repos[0])

        with pytest.raises(MountPlanningError, match="duplicate materialized") as error:
            build_mount_planning_view(manifest, lock, scanned, state, roots)

        assert "odoo-partner" in str(error.value)
        assert "username" not in str(error.value)
        assert "token" not in str(error.value)
        assert credential_url not in str(error.value)

    def test_rejects_materialized_commit_drift_without_leaking_url(self) -> None:
        credential_url = "https://username:token@github.com/ingadhoc/odoo-partner.git"
        manifest = _manifest(
            layers=[_git_layer(name="custom-x", repos=[GitRepo(url=credential_url, ref="19.0")])]
        )
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[ResolvedRepo(url=credential_url, ref="19.0", commit="sha-partner")],
                ),
            ],
        )
        roots = _container_roots(manifest)
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            ),
            ScannedRepo(
                path=Path("/mnt/custom/default/custom-x/odoo-partner"),
                url=credential_url,
                commit="sha-partner",
            ),
        ]
        state = MaterializedState(
            layers=[
                MaterializedLayer(
                    name="core",
                    repos=[MaterializedRepo(url=manifest.core.url, commit="sha-core")],
                ),
                MaterializedLayer(
                    name="custom-x",
                    repos=[MaterializedRepo(url=credential_url, commit="stale-partner")],
                ),
            ]
        )

        with pytest.raises(MountPlanningError, match="materialized commit drift") as error:
            build_mount_planning_view(manifest, lock, scanned, state, roots)

        assert "odoo-partner" in str(error.value)
        assert "username" not in str(error.value)
        assert "token" not in str(error.value)
        assert credential_url not in str(error.value)

    def test_container_path_stays_fixed_at_mnt_when_host_base_differs(self) -> None:
        host_base = Path("/custom/state/odoo-forge")
        host_roots = build_mount_roots(host_base)
        manifest = _manifest()
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
            ],
        )
        scanned = [
            ScannedRepo(
                path=host_roots["community"] / "core" / "odoo",
                url=manifest.core.url,
                commit="sha-core",
            )
        ]
        state = materialize_state(scanned, host_roots)

        view = build_mount_planning_view(manifest, lock, scanned, state, host_roots)

        assert view.mounts[0].source_path == host_roots["community"] / "core" / "odoo"
        assert view.mounts[0].container_path == Path("/mnt/community/core/odoo")

    def test_selects_a_valid_worktree_over_a_stale_read_only_counterpart(self) -> None:
        custom_url = "https://github.com/ingadhoc/odoo-partner.git"
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])
        roots = _container_roots(manifest)
        lock = Lockfile(
            generated_from=compute_manifest_hash(manifest),
            git_layers=[
                ResolvedLayer(
                    name="core",
                    repos=[ResolvedRepo(url=manifest.core.url, ref="19.0", commit="sha-core")],
                ),
                ResolvedLayer(
                    name="custom-x",
                    repos=[ResolvedRepo(url=custom_url, ref="19.0", commit="sha-partner")],
                ),
            ],
        )
        scanned = [
            ScannedRepo(
                path=Path("/mnt/community/core/odoo"),
                url=manifest.core.url,
                commit="sha-core",
            ),
            ScannedRepo(
                path=Path("/mnt/custom/default/custom-x/odoo-partner"),
                url=custom_url,
                commit="stale-partner",
            ),
            ScannedRepo(
                path=Path("/mnt/worktrees/custom-x/odoo-partner"),
                url=custom_url,
                commit="sha-partner",
            ),
        ]

        view = build_mount_planning_view(
            manifest, lock, scanned, materialize_state(scanned, roots), roots
        )

        assert isinstance(view, MountPlanningView)
        assert [
            (mount.layer, mount.source_path, mount.container_path, mount.read_only)
            for mount in view.mounts
        ] == [
            (
                "core",
                Path("/mnt/community/core/odoo"),
                Path("/mnt/community/core/odoo"),
                True,
            ),
            (
                "custom-x",
                Path("/mnt/worktrees/custom-x/odoo-partner"),
                Path("/mnt/custom/default/custom-x/odoo-partner"),
                False,
            ),
        ]


class TestPlanUnlock:
    def test_computes_source_dest_and_branch_for_a_custom_layer(self) -> None:
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])

        plan = plan_unlock(manifest, "custom-x", "https://github.com/ingadhoc/odoo-partner.git")

        assert plan.source == Path("/mnt/custom/default/custom-x/odoo-partner")
        assert plan.dest == Path("/mnt/worktrees/custom-x/odoo-partner")
        assert plan.branch == "unlock/custom-x/odoo-partner"

    def test_computes_source_for_the_core_layer(self) -> None:
        manifest = _manifest()

        plan = plan_unlock(manifest, "core", manifest.core.url)

        assert plan.source.parts[:2] == ("/", "mnt")
        assert "community" in plan.source.parts
        assert plan.dest == Path("/mnt/worktrees/core") / plan.source.name

    def test_honors_injected_roots_for_a_non_default_base(self) -> None:
        base = Path("/custom/state/odoo-forge")
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])
        roots = build_mount_roots(base, manifest)

        plan = plan_unlock(
            manifest, "custom-x", "https://github.com/ingadhoc/odoo-partner.git", roots
        )

        assert plan.source == roots["custom/default"] / "custom-x" / "odoo-partner"
        assert plan.dest == roots["worktrees"] / "custom-x" / "odoo-partner"

    def test_routes_the_enterprise_singleton_layer(self) -> None:
        manifest = _manifest(
            edition="enterprise",
            enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0"),
        )

        plan = plan_unlock(manifest, "enterprise", "https://github.com/odoo/enterprise.git")

        assert plan.source == Path("/mnt/enterprise/enterprise/enterprise")
        assert plan.dest == Path("/mnt/worktrees/enterprise/enterprise")
        assert plan.branch == "unlock/enterprise/enterprise"

    def test_unknown_layer_raises_projection_error(self) -> None:
        manifest = _manifest()

        with pytest.raises(ProjectionError, match="ghost-layer"):
            plan_unlock(manifest, "ghost-layer", "https://example.com/ghost.git")

    def test_rejects_undeclared_repo_with_same_basename(self) -> None:
        manifest = _manifest(layers=[_git_layer(name="custom-x", category="custom")])

        with pytest.raises(ProjectionError, match="does not belong to layer 'custom-x'"):
            plan_unlock(manifest, "custom-x", "https://attacker.example/other/odoo-partner.git")

    def test_override_uses_effective_fork_path_but_requires_declared_repo_identity(self) -> None:
        declared_url = "https://github.com/ingadhoc/odoo-partner.git"
        fork_url = "https://github.com/acme/partner-fork.git"
        manifest = _manifest(
            layers=[_git_layer(name="custom-x", category="custom")],
            overrides=[{"layer": "custom-x", "repo": declared_url, "fork": fork_url, "ref": "fix"}],
        )

        plan = plan_unlock(manifest, "custom-x", declared_url)

        assert plan.source == Path("/mnt/custom/default/custom-x/partner-fork")
        assert plan.dest == Path("/mnt/worktrees/custom-x/partner-fork")
        assert plan.branch == "unlock/custom-x/partner-fork"
        with pytest.raises(ProjectionError, match="does not belong to layer 'custom-x'"):
            plan_unlock(manifest, "custom-x", fork_url)


class TestOrderedAddonsRoots:
    def test_default_order_when_no_priority(self) -> None:
        manifest = _manifest(
            layers=[
                _git_layer(name="oca", category="oca"),
                _git_layer(name="adhoc", category="adhoc"),
            ]
        )

        result = projection.ordered_addons_roots(manifest)

        assert result == [
            Path("/mnt/worktrees"),
            Path("/mnt/community"),
            Path("/mnt/enterprise"),
            Path("/mnt/custom/adhoc"),
            Path("/mnt/custom/oca"),
        ]

    def test_priority_entries_come_first_in_declared_order(self) -> None:
        manifest = _manifest(
            layers=[
                _git_layer(name="ov", category="overrides"),
                _git_layer(name="oca", category="oca"),
            ],
            mount_priority=["custom/overrides", "worktrees"],
        )

        result = projection.ordered_addons_roots(manifest)

        # Listed roots first (exact order), then the rest in default order.
        assert result == [
            Path("/mnt/custom/overrides"),
            Path("/mnt/worktrees"),
            Path("/mnt/community"),
            Path("/mnt/enterprise"),
            Path("/mnt/custom/oca"),
        ]

    def test_a_custom_category_can_outrank_every_system_root(self) -> None:
        manifest = _manifest(
            layers=[_git_layer(name="ov", category="overrides")],
            mount_priority=["custom/overrides"],
        )

        result = projection.ordered_addons_roots(manifest)

        assert result[0] == Path("/mnt/custom/overrides")

    def test_honors_injected_base(self) -> None:
        manifest = _manifest(layers=[_git_layer(name="oca", category="oca")])

        result = projection.ordered_addons_roots(manifest, base=Path("/opt/mnt"))

        assert result == [
            Path("/opt/mnt/worktrees"),
            Path("/opt/mnt/community"),
            Path("/opt/mnt/enterprise"),
            Path("/opt/mnt/custom/oca"),
        ]
