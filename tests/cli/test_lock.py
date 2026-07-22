import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.manifest.artifacts import PublishedArtifactResolution
from odoo_forge.manifest.errors import RefNotFoundError
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.projection import ScannedRepo
from odoo_forge_cli import _composition, _support, main
from odoo_forge_cli.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

runner = CliRunner()


def _fake_enterprise_credential_resolver(handle: CredentialHandle) -> str:
    """Stand-in for the real SOPS+age resolver: `valid.project.yaml` declares
    `edition: enterprise`, so `lock`'s fail-fast preflight check now resolves
    the conventional Enterprise credential before writing anything — this
    fake always succeeds so pre-existing tests keep exercising the same
    `build_lock`/write behavior, unrelated to Slice 4's own coverage."""
    return "fake-enterprise-credential-for-tests"


@pytest.fixture(autouse=True)
def enterprise_credential_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "_make_enterprise_credential_resolver",
        lambda **kwargs: _fake_enterprise_credential_resolver,
    )


class _FakeSourceProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def resolve_ref(self, url: str, ref: str, env_overlay: dict[str, str] | None = None) -> str:
        self.calls.append((url, ref, env_overlay))
        return f"sha-{ref}"


class _FailingSourceProvider:
    def resolve_ref(self, url: str, ref: str, env_overlay: dict[str, str] | None = None) -> str:
        raise RefNotFoundError(url, ref)


class _FakePublishedArtifactResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def resolve(self, source: str, version: str) -> PublishedArtifactResolution:
        self.calls.append((source, version))
        return PublishedArtifactResolution(source, version, "sha256:" + "b" * 64)


@pytest.fixture(autouse=True)
def published_artifact_resolver(monkeypatch: pytest.MonkeyPatch) -> _FakePublishedArtifactResolver:
    resolver = _FakePublishedArtifactResolver()
    monkeypatch.setattr(_composition, "_make_published_artifact_resolver", lambda: resolver)
    return resolver


class _FakeProjectedWorkspaceProvider:
    """A `WorkspaceProvider` double whose `scan` reports a fully-projected
    workspace matching the lock written by `_FakeSourceProvider` — used to
    prove `validate`'s scan wiring reports no drift on a matching tree."""

    def __init__(self, scanned: list[ScannedRepo]) -> None:
        self._scanned = scanned

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        raise NotImplementedError

    def scan(self, roots: object) -> list[ScannedRepo]:
        return self._scanned

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def test_valid_manifest_writes_canonical_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    published_artifact_resolver: _FakePublishedArtifactResolver,
) -> None:
    fake_provider = _FakeSourceProvider()
    monkeypatch.setattr(_composition, "_make_provider", lambda: fake_provider)

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    lock_path = tmp_path / "project.lock"
    assert lock_path.exists()

    raw_lock = lock_path.read_text()
    lock = Lockfile.from_json(raw_lock)
    assert lock.schema_version == 2
    assert json.loads(raw_lock).keys() == {
        "generated_from",
        "git_layers",
        "published_layers",
        "schema_version",
    }
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].commit.startswith("sha-")
    assert lock.published_layers[0].model_dump() == {
        "name": "enterprise",
        "source": "registry://example/odoo-ee",
        "version": "19.0.1",
        "digest": "sha256:" + "b" * 64,
    }
    assert published_artifact_resolver.calls == [("registry://example/odoo-ee", "19.0.1")]

    # Integration proof: `edition: enterprise` now genuinely resolves the
    # enterprise layer THROUGH the credential wrapper (the prerequisite that
    # made `build_lock` resolve `manifest.enterprise` landed alongside the
    # credential wrapper) — the enterprise `resolve_ref` call carries the
    # askpass `env_overlay`, while the untouched `core` call does not.
    calls_by_url = {url: env_overlay for url, _ref, env_overlay in fake_provider.calls}
    assert calls_by_url["https://github.com/odoo/odoo.git"] is None
    enterprise_overlay = calls_by_url["https://github.com/odoo/enterprise.git"]
    assert enterprise_overlay is not None
    assert enterprise_overlay["GIT_ASKPASS"]


def test_core_ref_none_resolved_via_default_before_pinning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_composition, "_make_provider", lambda: _FakeSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(
        "name: minimal\n"
        "odoo_version: '19.0'\n"
        "edition: community\n"
        "core:\n"
        "  type: core\n"
        "client:\n"
        "  addons_path: client/addons\n"
    )

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    lock = Lockfile.from_json((tmp_path / "project.lock").read_text())
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].ref == "19.0"
    assert core_layer.repos[0].commit == "sha-19.0"


def test_resolution_error_exits_one_with_clean_message_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_composition, "_make_provider", lambda: _FailingSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert not (tmp_path / "project.lock").exists()


def test_lock_then_validate_round_trip_no_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`validate` reports no drift against a lock just written by `lock`.

    This only proves manifest<->lock hash agreement; it says nothing about
    the *content* of the written lock, so a direct structural assertion on
    the lock's layers is added below to prove the lock itself is correct.
    """
    monkeypatch.setattr(_composition, "_make_provider", lambda: _FakeSourceProvider())

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    lock_result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])
    assert lock_result.exit_code == 0

    lock = Lockfile.from_json((tmp_path / "project.lock").read_text())
    assert [layer.name for layer in lock.layers] == ["core", "enterprise", "localization"]
    core_layer = lock.layers[0]
    assert len(core_layer.repos) == 1
    assert core_layer.repos[0].commit == "sha-19.0"
    enterprise_layer = lock.layers[1]
    assert enterprise_layer.repos[0].url == "https://github.com/odoo/enterprise.git"
    assert enterprise_layer.repos[0].commit == "sha-19.0"
    localization_layer = lock.layers[2]
    assert [repo.url for repo in localization_layer.repos] == [
        "https://github.com/acme/odoo-argentina-ee.git"
    ]
    assert localization_layer.repos[0].url == "https://github.com/acme/odoo-argentina-ee.git"
    assert localization_layer.repos[0].ref == "custom-fix"
    assert localization_layer.repos[0].commit == "sha-custom-fix"

    # `validate` now scans the real mount roots (Slice 3): a fully-projected
    # workspace — simulated here via a fake `WorkspaceProvider.scan` matching
    # the lock exactly — reports no drift; an unprojected workspace would
    # correctly report `not_materialized` instead (see test_validate.py).
    monkeypatch.setattr(
        _composition,
        "_make_workspace_provider",
        lambda: _FakeProjectedWorkspaceProvider(
            [
                ScannedRepo(
                    path=Path("/mnt/community/core/odoo"),
                    url="https://github.com/odoo/odoo.git",
                    commit="sha-19.0",
                ),
                ScannedRepo(
                    path=Path("/mnt/enterprise/enterprise/enterprise"),
                    url="https://github.com/odoo/enterprise.git",
                    commit="sha-19.0",
                ),
                ScannedRepo(
                    path=Path("/mnt/enterprise/localization/odoo-argentina-ee"),
                    url="https://github.com/acme/odoo-argentina-ee.git",
                    commit="sha-custom-fix",
                ),
            ]
        ),
    )

    validate_result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert validate_result.exit_code == 0
    assert "no manifest/lock drift detected" in validate_result.output


def test_write_failure_exits_clean_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError during the atomic write is mapped to the same clean error
    contract as resolution/manifest failures — never a raw traceback."""
    monkeypatch.setattr(_composition, "_make_provider", lambda: _FakeSourceProvider())

    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _raise_os_error)

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert not (tmp_path / "project.lock").exists()


def test_write_failure_preserves_existing_lock_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a valid `project.lock` already exists, a failed re-write must leave
    it byte-identical — the atomic rename never truncates the original."""
    monkeypatch.setattr(_composition, "_make_provider", lambda: _FakeSourceProvider())

    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _raise_os_error)

    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())

    lock_path = tmp_path / "project.lock"
    original_content = '{"schema_version": 1, "generated_from": "original", "layers": []}'
    lock_path.write_text(original_content)

    result = runner.invoke(app, ["lock", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert lock_path.read_text() == original_content


def test_load_lock_uses_from_json_roundtrip(tmp_path: Path) -> None:
    """A lock written via `Lockfile.to_canonical_json()` reads back via `from_json()`."""
    lock = Lockfile(generated_from="deadbeef")
    lock_path = tmp_path / "project.lock"
    lock_path.write_text(lock.to_canonical_json())

    loaded = _support._load_lock(lock_path)

    assert loaded is not None
    assert loaded.generated_from == "deadbeef"
    assert loaded.schema_version == lock.schema_version


def test_load_lock_rejects_invalid_json(tmp_path: Path) -> None:
    from odoo_forge.manifest.errors import LockfileError

    lock_path = tmp_path / "project.lock"
    lock_path.write_text("{ not valid json")

    with pytest.raises(LockfileError):
        _support._load_lock(lock_path)


@pytest.mark.parametrize("schema_version", [3, "two"])
def test_validate_rejects_invalid_lock_version_without_traceback(
    tmp_path: Path, schema_version: object
) -> None:
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text((FIXTURES_DIR / "valid.project.yaml").read_text())
    (tmp_path / "project.lock").write_text(json.dumps({"schema_version": schema_version}))

    result = runner.invoke(app, ["validate", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "invalid lockfile" in result.output
    assert "Traceback" not in result.output
