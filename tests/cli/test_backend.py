from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.backend.errors import DockerUnavailableError, InstanceExistsError
from odoo_forge.backend.plan import BackendPlan
from odoo_forge.backend.status import InstanceRef, InstanceStatus, RoleStatus
from odoo_forge.manifest.errors import ScanError
from odoo_forge_cli import main
from odoo_forge_cli.main import app

runner = CliRunner()

_MANIFEST_TEXT = (
    "name: odoo-idp\n"
    "odoo_version: '19.0'\n"
    "edition: community\n"
    "core:\n"
    "  type: core\n"
    "  url: https://github.com/odoo/odoo.git\n"
    "  ref: '19.0'\n"
    "layers: []\n"
    "client:\n"
    "  addons_path: client/addons\n"
)


def _write_manifest(tmp_path: Path) -> Path:
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(_MANIFEST_TEXT)
    return project_yaml


class _FakeWorkspaceProvider:
    """No repos to scan for these tests: `scan` returns an empty list."""

    def __init__(self, scan_error: Exception | None = None) -> None:
        self._scan_error = scan_error

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        raise NotImplementedError

    def scan(self, roots: object) -> list[object]:
        if self._scan_error is not None:
            raise self._scan_error
        return []

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


class _FakeBackendProvider:
    """Records `run`/`status` calls; no docker, no I/O."""

    def __init__(
        self,
        run_result: InstanceRef | None = None,
        run_error: Exception | None = None,
        status_result: InstanceStatus | None = None,
    ) -> None:
        self.run_calls: list[BackendPlan] = []
        self.status_calls: list[InstanceRef] = []
        self._run_result = run_result
        self._run_error = run_error
        self._status_result = status_result

    def run(self, plan: BackendPlan) -> InstanceRef:
        self.run_calls.append(plan)
        if self._run_error is not None:
            raise self._run_error
        assert self._run_result is not None
        return self._run_result

    def status(self, ref: InstanceRef) -> InstanceStatus:
        self.status_calls.append(ref)
        assert self._status_result is not None
        return self._status_result

    def stop(self, ref: InstanceRef) -> None:
        raise NotImplementedError

    def logs(self, ref: InstanceRef, role: object) -> str:
        raise NotImplementedError

    def exec(self, ref: InstanceRef, argv: object) -> object:
        raise NotImplementedError


def test_run_succeeds_prints_instance_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    expected_ref = InstanceRef(
        project="odoo-idp",
        instance="default",
        network="odoo-forge-odoo-idp-default",
        postgres_container="odoo-forge-odoo-idp-default-db",
        odoo_container="odoo-forge-odoo-idp-default-odoo",
    )
    fake_backend = _FakeBackendProvider(run_result=expected_ref)
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_backend.run_calls) == 1
    assert fake_backend.run_calls[0].network.name == "odoo-forge-odoo-idp-default"
    assert expected_ref.odoo_container in result.output
    assert expected_ref.postgres_container in result.output


def test_run_docker_unavailable_single_line_exit1_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        run_error=DockerUnavailableError("docker daemon is not reachable")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


def test_status_reports_not_running_without_raising_for_absent_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    not_running = RoleStatus(running=False, state="exited", ready=False)
    fake_backend = _FakeBackendProvider(
        status_result=InstanceStatus(odoo=not_running, postgres=not_running)
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["status", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_backend.status_calls) == 1
    assert "running=False" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["run", "status"])
def test_scan_error_from_corrupted_checkout_exits_clean_one_error(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `ScanError` is a `WorkspaceError` -> `ManifestError`, NOT a
    # `BackendError` — `run`/`status` must still catch it (mirrors
    # `project`/`validate`'s identical `scan()`/`materialize_state()`
    # boundary; both commands share that exact call).
    fake_workspace = _FakeWorkspaceProvider(
        scan_error=ScanError("cannot read materialized repo state at '/mnt/community/core'")
    )
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)
    monkeypatch.setattr(main, "_make_backend_provider", lambda: _FakeBackendProvider())

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, [command, "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


def test_run_instance_exists_exits_clean_one_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The `run` docstring/comment claims `InstanceExistsError` is handled by
    # the same `BackendError` boundary as every other backend failure — pin
    # that path explicitly rather than relying on the generic
    # `DockerUnavailableError` test to stand in for the whole family.
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        run_error=InstanceExistsError("instance 'default' already exists")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["run", "status"])
def test_missing_manifest_exits_clean_one_error(command: str, tmp_path: Path) -> None:
    # Not a copy-paste-assumed path: `run`/`status` share `validate`'s
    # manifest-read boundary, but each has its own command wiring to verify.
    missing_manifest = tmp_path / "does-not-exist.yaml"

    result = runner.invoke(app, [command, "--manifest", str(missing_manifest)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["run", "status"])
def test_malformed_manifest_exits_clean_one_error(command: str, tmp_path: Path) -> None:
    malformed = tmp_path / "project.yaml"
    malformed.write_text("name: [unterminated\n")

    result = runner.invoke(app, [command, "--manifest", str(malformed)])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
