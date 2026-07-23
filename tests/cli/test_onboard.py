from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from odoo_forge.backend.errors import BackendError
from odoo_forge.backend.plan import BackendPlan
from odoo_forge.backend.status import InstanceRef
from odoo_forge.credentials.errors import CredentialError
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.manifest.errors import CheckoutError, ScanError
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import ScannedRepo, build_mount_roots
from odoo_forge.manifest.schema import Manifest
from odoo_forge.project_catalog.models import (
    CatalogAliases,
    CatalogDefaults,
    CatalogRecord,
    CatalogRepoRef,
    CatalogSourceContext,
    ManifestRef,
    ProjectCatalogRequest,
)
from odoo_forge_catalog.errors import CatalogSourceError
from odoo_forge_cli import _composition, _support
from odoo_forge_cli.main import app

runner = CliRunner()

_MANIFEST_TEXT = (
    "name: onboarding-project\n"
    "odoo_version: '19.0'\n"
    "edition: community\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "layers:\n"
    "  - type: git\n"
    "    name: custom-x\n"
    "    repos:\n"
    "      - url: https://example.com/custom-x.git\n"
    "        ref: main\n"
    "client:\n"
    "  addons_path: client/addons\n"
)

# Mirror the per-manifest HOST table `onboard` builds internally
# (`build_mount_roots(_resolve_mount_base(), parsed)`), so the fake provider's
# scanned paths line up with the roots the command actually resolves. The
# `custom-x` layer defaults to the `custom` category, nesting under
# `custom/default` in the pure mount model.
_HOST_ROOTS = build_mount_roots(
    _support._resolve_mount_base(), Manifest.model_validate(yaml.safe_load(_MANIFEST_TEXT))
)


class _FakeWorkspaceProvider:
    def __init__(
        self,
        *,
        scan_error: bool = False,
        fail_checkout: bool = False,
        stale_checkout: bool = False,
        post_checkout_stale: bool = False,
    ) -> None:
        self.checkout_calls: list[tuple[str, str, Path]] = []
        self._scan_error = scan_error
        self._fail_checkout = fail_checkout
        self._stale_checkout = stale_checkout
        self._post_checkout_stale = post_checkout_stale

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        if self._fail_checkout:
            raise CheckoutError(f"cannot reach remote for '{url}'")
        self.checkout_calls.append((url, commit, dest))

    def scan(self, roots: object) -> list[ScannedRepo]:
        if self._scan_error:
            raise ScanError("cannot inspect workspace")
        if not self.checkout_calls:
            if self._stale_checkout:
                return [
                    ScannedRepo(
                        path=_HOST_ROOTS["community"] / "core" / "odoo",
                        url="https://github.com/odoo/odoo.git",
                        commit="stale-sha",
                    ),
                    ScannedRepo(
                        path=_HOST_ROOTS["custom/default"] / "custom-x" / "custom-x",
                        url="https://example.com/custom-x.git",
                        commit="stale-sha",
                    ),
                ]
            return []
        return [
            ScannedRepo(
                path=dest,
                url=url,
                commit="stale-sha" if self._stale_checkout or self._post_checkout_stale else commit,
            )
            for url, commit, dest in self.checkout_calls
        ]

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def _write_manifest_and_lock(tmp_path: Path, *, generated_from: str | None = None) -> Path:
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(_MANIFEST_TEXT)
    manifest = Manifest.model_validate(yaml.safe_load(_MANIFEST_TEXT))
    lock = Lockfile(
        generated_from=generated_from or compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="core-sha"
                    )
                ],
            ),
            ResolvedLayer(
                name="custom-x",
                repos=[
                    ResolvedRepo(
                        url="https://example.com/custom-x.git", ref="main", commit="custom-sha"
                    )
                ],
            ),
        ],
    )
    (tmp_path / "project.lock").write_text(lock.to_canonical_json())
    return manifest_path


def test_onboard_projects_valid_local_inputs_and_prints_next_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert len(provider.checkout_calls) == 2
    assert "workspace" in result.output.lower()
    assert "next" in result.output.lower()
    assert "runtime" not in result.output.lower()
    assert "database" not in result.output.lower()


def test_onboard_rejects_missing_lock_before_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = tmp_path / "project.yaml"
    manifest.write_text(_MANIFEST_TEXT)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "project.lock" in result.output
    assert not provider.checkout_calls


@pytest.mark.parametrize(
    ("manifest_text", "lock_text"),
    [
        ("name: [malformed", None),
        (_MANIFEST_TEXT, "{malformed-json"),
    ],
)
def test_onboard_rejects_malformed_local_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_text: str,
    lock_text: str | None,
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = tmp_path / "project.yaml"
    manifest.write_text(manifest_text)
    if lock_text is not None:
        (tmp_path / "project.lock").write_text(lock_text)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert not provider.checkout_calls


def test_onboard_rejects_manifest_lock_drift_before_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path, generated_from="stale-manifest-hash")

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "drift" in result.output.lower()
    assert not provider.checkout_calls


def test_onboard_rejects_stale_checkout_evidence_before_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(stale_checkout=True)
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "drift" in result.output.lower() or "stale" in result.output.lower()
    assert not provider.checkout_calls


def test_onboard_reports_post_projection_drift_as_safety_net(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(post_checkout_stale=True)
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "drift" in result.output.lower()
    # Preflight passed and checkout ran; the drift was caught only by the
    # post-projection safety-net re-scan, not by preflight.
    assert provider.checkout_calls
    assert "next" not in result.output.lower()


def test_onboard_reports_scan_failure_without_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(scan_error=True)
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "cannot inspect workspace" in result.output
    assert not provider.checkout_calls


def _write_module(root: Path, name: str, content: str) -> None:
    module_dir = root / name
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "__manifest__.py").write_text(content, encoding="utf-8")


def test_onboard_rejects_missing_module_dependency_after_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`forge onboard` is a valid path to a fully materialized workspace that
    never goes through `forge validate` — it MUST run the same
    module-dependency check once the workspace is confirmed materialized, not
    leave it to an optional later `forge validate` call."""
    base = tmp_path / "mount-base"
    monkeypatch.setattr(_support, "_resolve_mount_base", lambda: base)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    _write_module(base / "community", "mod_a", "{'name': 'Mod A', 'depends': ['mod_missing']}")

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "mod_a" in result.output
    assert "mod_missing" in result.output
    # The workspace WAS fully materialized (checkout ran) before the
    # dependency check rejected it — this proves the check runs against the
    # real, projected addons_path, not before materialization.
    assert provider.checkout_calls
    assert "next" not in result.output.lower()


def test_onboard_succeeds_when_module_dependencies_are_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "mount-base"
    monkeypatch.setattr(_support, "_resolve_mount_base", lambda: base)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    _write_module(base / "community", "mod_b", "{'name': 'Mod B'}")
    _write_module(base / "community", "mod_a", "{'name': 'Mod A', 'depends': ['mod_b']}")

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "next" in result.output.lower()


def test_onboard_reports_checkout_failure_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeWorkspaceProvider(fail_checkout=True)
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest)])

    assert result.exit_code == 1
    assert "cannot reach remote" in result.output
    assert "Traceback" not in result.output


# -- Dual-mode dispatch: catalog-driven `onboard <cliente>` ------------------


class _FakeCatalogIndex:
    """Records `find_matches` calls; returns pre-seeded matches or raises."""

    def __init__(
        self,
        records: list[CatalogRecord] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.find_matches_calls: list[ProjectCatalogRequest] = []
        self._records = records if records is not None else []
        self._error = error

    def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]:
        self.find_matches_calls.append(request)
        if self._error is not None:
            raise self._error
        return self._records


class _FakeCatalogBackendProvider:
    """Records `run` calls; no docker, no I/O."""

    def __init__(
        self, run_result: InstanceRef | None = None, run_error: Exception | None = None
    ) -> None:
        self.run_calls: list[BackendPlan] = []
        self._run_result = run_result
        self._run_error = run_error

    def run(self, plan: BackendPlan) -> InstanceRef:
        self.run_calls.append(plan)
        if self._run_error is not None:
            raise self._run_error
        assert self._run_result is not None
        return self._run_result


def _make_catalog_record(
    manifest_path: Path,
    *,
    record_id: str = "acme-1",
    client_key: str = "acme",
    target_default: str = "local",
    data_policy_default: str = "synthetic",
    manifest_ref: bool = True,
) -> CatalogRecord:
    return CatalogRecord(
        record_id=record_id,
        client_key=client_key,
        project_key=f"{client_key}-project",
        aliases=CatalogAliases(),
        manifest_ref=(
            ManifestRef(manifest_name=client_key, manifest_path=str(manifest_path))
            if manifest_ref
            else None
        ),
        source_context=CatalogSourceContext(
            source_set_id=f"{client_key}-src",
            repos=[CatalogRepoRef(url="https://example.com/x.git", ref="main", role="custom")],
        ),
        defaults=CatalogDefaults(data_policy=data_policy_default, target=target_default),
    )


_EXPECTED_CATALOG_REF = InstanceRef(
    project="onboarding-project",
    instance="default",
    network="odoo-forge-onboarding-project-default",
    postgres_container="odoo-forge-onboarding-project-default-db",
    odoo_container="odoo-forge-onboarding-project-default-odoo",
)


def test_onboard_rejects_both_manifest_and_client_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _FakeCatalogIndex()
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)
    manifest = _write_manifest_and_lock(tmp_path)

    result = runner.invoke(app, ["onboard", "--manifest", str(manifest), "some-client"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "not both" in result.output
    assert not catalog.find_matches_calls
    assert not provider.checkout_calls
    assert not backend.run_calls


def test_onboard_rejects_neither_manifest_nor_client_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _FakeCatalogIndex()
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "requires" in result.output
    assert not catalog.find_matches_calls
    assert not provider.checkout_calls
    assert not backend.run_calls


def test_onboard_catalog_driven_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _write_manifest_and_lock(tmp_path)
    catalog = _FakeCatalogIndex(records=[_make_catalog_record(manifest)])
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider(run_result=_EXPECTED_CATALOG_REF)
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 0
    assert len(provider.checkout_calls) == 2
    assert len(backend.run_calls) == 1
    assert "running" in result.output.lower()
    assert _EXPECTED_CATALOG_REF.odoo_container in result.output


def test_onboard_catalog_driven_backend_failure_no_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write_manifest_and_lock(tmp_path)
    catalog = _FakeCatalogIndex(records=[_make_catalog_record(manifest)])
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider(run_error=BackendError("instance creation failed"))
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "running" not in result.output.lower()
    assert len(backend.run_calls) == 1


def test_onboard_catalog_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _FakeCatalogIndex(records=[])
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "unknown-client"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "catalog-not-found" in result.output
    assert not provider.checkout_calls
    assert not backend.run_calls


def test_onboard_catalog_ambiguous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _write_manifest_and_lock(tmp_path)
    catalog = _FakeCatalogIndex(
        records=[
            _make_catalog_record(manifest, record_id="acme-1"),
            _make_catalog_record(manifest, record_id="acme-2"),
        ]
    )
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "ambiguous-resolution" in result.output
    assert not provider.checkout_calls
    assert not backend.run_calls


def test_onboard_catalog_invalid_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _write_manifest_and_lock(tmp_path)
    catalog = _FakeCatalogIndex(records=[_make_catalog_record(manifest, manifest_ref=False)])
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "invalid-catalog" in result.output
    assert not provider.checkout_calls
    assert not backend.run_calls


def test_onboard_catalog_source_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _FakeCatalogIndex(error=CatalogSourceError("malformed catalog.yaml"))
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "malformed catalog.yaml" in result.output
    assert "catalog-not-found" not in result.output
    assert "ambiguous-resolution" not in result.output
    assert "invalid-catalog" not in result.output
    assert not provider.checkout_calls
    assert not backend.run_calls


def test_onboard_catalog_pass_through_defaults_not_actioned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write_manifest_and_lock(tmp_path)
    catalog = _FakeCatalogIndex(
        records=[
            _make_catalog_record(
                manifest, target_default="remote-ec2", data_policy_default="seeded"
            )
        ]
    )
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider(run_result=_EXPECTED_CATALOG_REF)
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 0
    assert len(backend.run_calls) == 1
    assert "running" in result.output.lower()


def test_onboard_catalog_rejects_missing_enterprise_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catalog-resolved manifest with `edition: enterprise` and missing
    credential should fail the same way `--manifest` mode does — fail fast
    before any checkout attempt."""
    # Use enterprise edition: manifest doesn't require an enterprise layer,
    # only the edition flag triggers the preflight check
    enterprise_manifest_text = (
        "name: onboarding-project\n"
        "odoo_version: '19.0'\n"
        "edition: enterprise\n"
        "core:\n"
        "  type: core\n"
        "  url: https://github.com/odoo/odoo.git\n"
        "  ref: '19.0'\n"
        "layers:\n"
        "  - type: git\n"
        "    name: custom-x\n"
        "    repos:\n"
        "      - url: https://example.com/custom-x.git\n"
        "        ref: main\n"
        "client:\n"
        "  addons_path: client/addons\n"
    )
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(enterprise_manifest_text)
    manifest = Manifest.model_validate(yaml.safe_load(enterprise_manifest_text))
    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="core-sha"
                    )
                ],
            ),
            ResolvedLayer(
                name="custom-x",
                repos=[
                    ResolvedRepo(
                        url="https://example.com/custom-x.git", ref="main", commit="custom-sha"
                    )
                ],
            ),
        ],
    )
    (tmp_path / "project.lock").write_text(lock.to_canonical_json())

    catalog = _FakeCatalogIndex(records=[_make_catalog_record(manifest_path)])
    monkeypatch.setattr(_composition, "_make_catalog_index", lambda: catalog)
    provider = _FakeWorkspaceProvider()
    monkeypatch.setattr(_composition, "_make_workspace_provider", lambda: provider)
    backend = _FakeCatalogBackendProvider()
    monkeypatch.setattr(_composition, "_make_backend_provider", lambda **_kwargs: backend)

    # Monkeypatch the credential resolver to raise CredentialError
    def failing_resolver(**_kwargs):  # type: ignore[no-untyped-def]
        def resolver(handle: CredentialHandle) -> str:
            raise CredentialError("SOPS key not found or not usable")

        return resolver

    monkeypatch.setattr(
        "odoo_forge_cli.commands.manifest._make_enterprise_credential_resolver",
        failing_resolver,
    )

    result = runner.invoke(app, ["onboard", "acme"])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Enterprise credential" in result.output
    # Crucial: no workspace checkout should have been attempted (fail-fast)
    assert not provider.checkout_calls
    # No backend invocation either
    assert not backend.run_calls
