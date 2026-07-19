from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from odoo_forge.backend.errors import (
    DockerUnavailableError,
    ImageAuthorizationError,
    ImageNotFoundError,
    InstanceExistsError,
    InstanceNotFoundError,
)
from odoo_forge.backend.plan import BackendPlan, ContainerRole
from odoo_forge.backend.status import ExecResult, InstanceRef, InstanceStatus, RoleStatus
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.manifest.errors import ScanError
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedGitLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import ScannedRepo, build_mount_roots
from odoo_forge.manifest.schema import Manifest
from odoo_forge_cli import main
from odoo_forge_cli.main import app
from odoo_forge_cli.main import plan_backend as original_plan_backend  # type: ignore[attr-defined]
from odoo_forge_docker.credential_injection import SopsCommandResolver
from odoo_forge_docker.provider import DockerBackendProvider

runner = CliRunner()

_CORE_URL = "https://github.com/odoo/odoo.git"
_CORE_COMMIT = "a" * 40

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
    (tmp_path / "project.lock").write_text(
        Lockfile(
            generated_from=compute_manifest_hash(
                Manifest.model_validate(yaml.safe_load(_MANIFEST_TEXT))
            ),
            git_layers=[
                ResolvedGitLayer(
                    name="core",
                    repos=[ResolvedRepo(url=_CORE_URL, ref="19.0", commit=_CORE_COMMIT)],
                )
            ],
        ).to_canonical_json()
    )
    return project_yaml


def _write_manifest_with_backend_http_port(tmp_path: Path, http_port: int) -> Path:
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(_MANIFEST_TEXT + f"backend:\n  odoo:\n    http_port: {http_port}\n")
    (tmp_path / "project.lock").write_text(
        Lockfile(
            generated_from=compute_manifest_hash(
                Manifest.model_validate(yaml.safe_load(project_yaml.read_text()))
            ),
            git_layers=[
                ResolvedGitLayer(
                    name="core",
                    repos=[ResolvedRepo(url=_CORE_URL, ref="19.0", commit=_CORE_COMMIT)],
                )
            ],
        ).to_canonical_json()
    )
    return project_yaml


class _FakeWorkspaceProvider:
    """Returns complete core evidence unless a test selects a failure mode."""

    def __init__(
        self, scan_error: Exception | None = None, scanned: list[ScannedRepo] | None = None
    ) -> None:
        self._scan_error = scan_error
        self._scanned = (
            scanned
            if scanned is not None
            else [
                ScannedRepo(
                    path=Path("/mnt/community/core/odoo"), url=_CORE_URL, commit=_CORE_COMMIT
                )
            ]
        )

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        raise NotImplementedError

    def scan(self, roots: object) -> list[ScannedRepo]:
        if self._scan_error is not None:
            raise self._scan_error
        return self._scanned

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


@pytest.mark.parametrize(
    ("prepare", "workspace"),
    [
        (lambda manifest: manifest.with_name("project.lock").unlink(), _FakeWorkspaceProvider()),
        (lambda _manifest: None, _FakeWorkspaceProvider(scanned=[])),
        (
            lambda _manifest: None,
            _FakeWorkspaceProvider(
                scan_error=ScanError("cannot read materialized repo state at '/mnt/community/core'")
            ),
        ),
        (
            lambda _manifest: None,
            _FakeWorkspaceProvider(
                scanned=[
                    ScannedRepo(
                        path=Path("/mnt/community/core/odoo"),
                        url=_CORE_URL,
                        commit="b" * 40,
                    )
                ]
            ),
        ),
    ],
    ids=["missing-lock", "incomplete-evidence", "malformed-evidence", "stale-evidence"],
)
def test_run_fails_closed_before_provider_for_invalid_workspace_evidence(
    prepare: object,
    workspace: _FakeWorkspaceProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_backend = _FakeBackendProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: workspace)
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)
    project_yaml = _write_manifest(tmp_path)

    prepare(project_yaml)  # type: ignore[operator]
    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert len(fake_backend.run_calls) == 0


class _FakeBackendProvider:
    """Records `run`/`status` calls; no docker, no I/O."""

    def __init__(
        self,
        run_result: InstanceRef | None = None,
        run_error: Exception | None = None,
        status_result: InstanceStatus | None = None,
        stop_error: Exception | None = None,
        logs_result: str | None = None,
        logs_error: Exception | None = None,
        exec_result: ExecResult | None = None,
        exec_error: Exception | None = None,
    ) -> None:
        self.run_calls: list[BackendPlan] = []
        self.status_calls: list[InstanceRef] = []
        self.stop_calls: list[InstanceRef] = []
        self.logs_calls: list[tuple[InstanceRef, ContainerRole]] = []
        self.exec_calls: list[tuple[InstanceRef, tuple[str, ...]]] = []
        self._run_result = run_result
        self._run_error = run_error
        self._status_result = status_result
        self._stop_error = stop_error
        self._logs_result = logs_result
        self._logs_error = logs_error
        self._exec_result = exec_result
        self._exec_error = exec_error

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
        self.stop_calls.append(ref)
        if self._stop_error is not None:
            raise self._stop_error

    def logs(self, ref: InstanceRef, role: ContainerRole) -> str:
        self.logs_calls.append((ref, role))
        if self._logs_error is not None:
            raise self._logs_error
        assert self._logs_result is not None
        return self._logs_result

    def exec(self, ref: InstanceRef, argv: Sequence[str]) -> ExecResult:
        self.exec_calls.append((ref, tuple(argv)))
        if self._exec_error is not None:
            raise self._exec_error
        assert self._exec_result is not None
        return self._exec_result


def test_run_succeeds_prints_instance_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_backend.run_calls) == 1
    assert fake_backend.run_calls[0].network.name == "odoo-forge-odoo-idp-default"
    assert expected_ref.odoo_container in result.output
    assert expected_ref.postgres_container in result.output


def test_run_scans_and_materializes_with_the_resolved_host_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run` must thread the resolved HOST mount table — not the fixed
    container table — into
    `workspace_provider.scan`/`materialize_state`/`build_mount_planning_view`."""
    base = Path("/custom/state/odoo-forge")
    monkeypatch.setattr(main, "_resolve_mount_base", lambda: base)
    custom_roots = build_mount_roots(base, Manifest.model_validate(yaml.safe_load(_MANIFEST_TEXT)))

    scan_calls: list[object] = []
    scanned = [
        ScannedRepo(
            path=custom_roots["community"] / "core" / "odoo", url=_CORE_URL, commit=_CORE_COMMIT
        )
    ]

    class _RecordingWorkspaceProvider:
        def checkout(self, url: str, commit: str, dest: Path) -> None:
            raise NotImplementedError

        def scan(self, roots: object) -> list[ScannedRepo]:
            scan_calls.append(roots)
            return scanned

        def promote(self, source: Path, dest: Path, branch: str) -> None:
            raise NotImplementedError

    monkeypatch.setattr(main, "_make_workspace_provider", lambda: _RecordingWorkspaceProvider())

    expected_ref = InstanceRef(
        project="odoo-idp",
        instance="default",
        network="odoo-forge-odoo-idp-default",
        postgres_container="odoo-forge-odoo-idp-default-db",
        odoo_container="odoo-forge-odoo-idp-default-odoo",
    )
    fake_backend = _FakeBackendProvider(run_result=expected_ref)
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert scan_calls == [list(custom_roots.values())]


def test_run_binds_opaque_credentials_at_the_composition_root(
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
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    captured: dict[str, object] = {}

    def _capture_plan_backend(*args: object, **kwargs: object) -> BackendPlan:
        captured.update(kwargs)
        return original_plan_backend(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(main, "plan_backend", _capture_plan_backend)

    result = runner.invoke(app, ["run", "--manifest", str(_write_manifest(tmp_path))])

    assert result.exit_code == 0
    credentials = captured["credentials"]
    assert credentials == BackendCredentialBindings(
        postgres_password=CredentialHandle("local-backend/postgres-password"),
        odoo_db_password=CredentialHandle("local-backend/odoo-db-password"),
    )


def test_default_backend_composition_configures_a_sops_resolver_for_the_manifest_directory(
    tmp_path: Path,
) -> None:
    credentials_file = tmp_path / "project" / "credentials.sops.yaml"

    provider = main._make_backend_provider(credentials_file=credentials_file)

    assert isinstance(provider, DockerBackendProvider)
    assert isinstance(provider._credential_injector._resolver, SopsCommandResolver)
    assert provider._credential_injector._resolver._credentials_file == credentials_file


def test_run_scopes_sops_resolution_to_the_selected_manifest(
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
    captured: dict[str, Path] = {}

    def make_backend_provider(**kwargs: Path) -> _FakeBackendProvider:
        captured.update(kwargs)
        return _FakeBackendProvider(run_result=expected_ref)

    monkeypatch.setattr(main, "_make_backend_provider", make_backend_provider)
    manifest_dir = tmp_path / "selected-project"
    manifest_dir.mkdir()
    manifest = _write_manifest(manifest_dir)

    result = runner.invoke(app, ["run", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert captured["credentials_file"] == manifest.resolve().parent / "credentials.sops.yaml"


def test_run_with_odoo_image_ref_passes_canonical_digest_to_planner(
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
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest(tmp_path)
    odoo_image_ref = "ghcr.io/odoo/odoo@sha256:" + "b" * 64

    result = runner.invoke(
        app,
        ["run", "--manifest", str(project_yaml), "--odoo-image-ref", odoo_image_ref],
    )

    assert result.exit_code == 0
    assert len(fake_backend.run_calls) == 1
    assert fake_backend.run_calls[0].odoo.image == odoo_image_ref
    assert expected_ref.odoo_container in result.output


def test_run_passes_manifest_configured_odoo_http_port_to_backend_plan(
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
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest_with_backend_http_port(tmp_path, 18069)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_backend.run_calls) == 1
    assert fake_backend.run_calls[0].odoo.ports == {"8069": 18069, "8072": None}


def test_run_rejects_non_digest_odoo_image_ref_before_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider()
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        ["run", "--manifest", str(project_yaml), "--odoo-image-ref", "ghcr.io/odoo/odoo:19.0"],
    )

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output
    assert len(fake_backend.run_calls) == 0


def test_run_docker_unavailable_single_line_exit1_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        run_error=DockerUnavailableError("docker daemon is not reachable")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("run_error", "expected_message"),
    [
        (
            ImageNotFoundError("image not found: ghcr.io/odoo/odoo@sha256:" + "c" * 64),
            "image not found: ghcr.io/odoo/odoo@sha256:" + "c" * 64,
        ),
        (
            ImageAuthorizationError(
                "registry authorization denied for ghcr.io/odoo/odoo@sha256:" + "d" * 64
            ),
            "registry authorization denied for ghcr.io/odoo/odoo@sha256:" + "d" * 64,
        ),
    ],
)
def test_run_pull_failures_exit_clean_single_line_and_keep_diagnostic(
    run_error: Exception,
    expected_message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(run_error=run_error)
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["run", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.strip() == f"error: {expected_message}"
    assert "Traceback" not in result.output
    assert len(fake_backend.run_calls) == 1


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


@pytest.mark.parametrize("command", ["run"])
def test_scan_error_from_corrupted_checkout_exits_clean_one_error(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `run` needs materialized workspace state and must still translate a
    # `ScanError` into a clean CLI failure.
    fake_workspace = _FakeWorkspaceProvider(
        scan_error=ScanError("cannot read materialized repo state at '/mnt/community/core'")
    )
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: _FakeBackendProvider())

    project_yaml = _write_manifest(tmp_path)
    args = [command, "--manifest", str(project_yaml)]
    if command == "exec":
        args += ["--", "echo", "hi"]

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["status", "stop", "logs", "exec"])
def test_instance_commands_do_not_scan_workspace(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_created() -> _FakeWorkspaceProvider:
        raise AssertionError("instance identity must not require a workspace scan")

    not_running = RoleStatus(running=False, state="exited", ready=False)
    fake_backend = _FakeBackendProvider(
        status_result=InstanceStatus(odoo=not_running, postgres=not_running),
        logs_result="captured logs",
        exec_result=ExecResult(exit_code=0, stdout="captured output", stderr=""),
    )
    monkeypatch.setattr(main, "_make_workspace_provider", fail_if_created)
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

    args = [command, "--manifest", str(_write_manifest(tmp_path))]
    if command == "exec":
        args += ["--", "echo", "hi"]

    result = runner.invoke(app, args)

    assert result.exit_code == 0


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
    monkeypatch.setattr(main, "_make_backend_provider", lambda **_kwargs: fake_backend)

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


@pytest.mark.parametrize("command", ["stop", "logs", "exec"])
def test_instance_command_manifest_validation_errors_are_field_oriented_and_safe(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "DO-NOT-RENDER-THIS-SECRET"
    invalid_manifest = tmp_path / "project.yaml"
    invalid_manifest.write_text(
        _MANIFEST_TEXT.replace("odoo_version: '19.0'", "odoo_version: 19").replace(
            "edition: community", f"edition: {secret}"
        )
    )
    backend_provider_created = False

    def make_backend_provider(**_kwargs: object) -> _FakeBackendProvider:
        nonlocal backend_provider_created
        backend_provider_created = True
        return _FakeBackendProvider()

    monkeypatch.setattr(main, "_make_backend_provider", make_backend_provider)
    args = [command, "--manifest", str(invalid_manifest)]
    if command == "exec":
        args += ["--", "echo", "hi"]

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert result.output.splitlines() == [
        "error: odoo_version: Input should be a valid string",
        "error: edition: Input should be 'community' or 'enterprise'",
    ]
    assert secret not in result.output
    assert "validation errors for Manifest" not in result.output
    assert "Traceback" not in result.output
    assert backend_provider_created is False


def test_run_rejects_invalid_backend_bind_host_before_provider_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_manifest = tmp_path / "project.yaml"
    invalid_manifest.write_text(_MANIFEST_TEXT + "backend:\n  odoo:\n    bind_host: odoo.local\n")
    backend_provider_created = False

    def make_backend_provider(**_kwargs: object) -> _FakeBackendProvider:
        nonlocal backend_provider_created
        backend_provider_created = True
        return _FakeBackendProvider()

    monkeypatch.setattr(main, "_make_backend_provider", make_backend_provider)

    result = runner.invoke(app, ["run", "--manifest", str(invalid_manifest)])

    assert result.exit_code == 1
    assert result.output.splitlines() == [
        "error: backend.odoo.bind_host: Value error, bind_host must be a valid IPv4 address"
    ]
    assert backend_provider_created is False
    assert "Traceback" not in result.output


def test_stop_succeeds_calls_provider_with_derived_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider()
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["stop", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_backend.stop_calls) == 1
    assert fake_backend.stop_calls[0].project == "odoo-idp"


def test_stop_unknown_instance_exits_nonzero_single_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        stop_error=InstanceNotFoundError("instance 'default' does not exist")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["stop", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


def test_logs_prints_role_selected_log_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(logs_result="2026-07-08T00:00:00 odoo booted")
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["logs", "--manifest", str(project_yaml), "--role", "postgres"])

    assert result.exit_code == 0
    assert "odoo booted" in result.output
    assert len(fake_backend.logs_calls) == 1
    assert fake_backend.logs_calls[0][1] == "postgres"


def test_logs_defaults_to_odoo_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(logs_result="log text")
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["logs", "--manifest", str(project_yaml)])

    assert result.exit_code == 0
    assert len(fake_backend.logs_calls) == 1
    assert fake_backend.logs_calls[0][1] == "odoo"


def test_logs_absent_instance_exits_clean_one_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        logs_error=InstanceNotFoundError("instance 'default' does not exist")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["logs", "--manifest", str(project_yaml)])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


def test_exec_prints_stdout_and_propagates_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        exec_result=ExecResult(exit_code=3, stdout="out-line", stderr="err-line")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(
        app, ["exec", "--manifest", str(project_yaml), "--", "python3", "-c", "1"]
    )

    assert result.exit_code == 3
    assert "out-line" in result.output
    assert "err-line" in result.output
    assert len(fake_backend.exec_calls) == 1
    assert fake_backend.exec_calls[0][1] == ("python3", "-c", "1")


def test_exec_absent_instance_exits_clean_one_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        exec_error=InstanceNotFoundError("instance 'default' does not exist")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["exec", "--manifest", str(project_yaml), "--", "echo", "hi"])

    assert result.exit_code == 1
    assert result.output.count("error:") == 1
    assert "Traceback" not in result.output


def test_logs_invalid_role_exits_clean_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)
    monkeypatch.setattr(main, "_make_backend_provider", lambda: _FakeBackendProvider())

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["logs", "--manifest", str(project_yaml), "--role", "bogus"])

    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_exec_success_exits_zero_prints_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_workspace = _FakeWorkspaceProvider()
    monkeypatch.setattr(main, "_make_workspace_provider", lambda: fake_workspace)

    fake_backend = _FakeBackendProvider(
        exec_result=ExecResult(exit_code=0, stdout="all good", stderr="")
    )
    monkeypatch.setattr(main, "_make_backend_provider", lambda: fake_backend)

    project_yaml = _write_manifest(tmp_path)

    result = runner.invoke(app, ["exec", "--manifest", str(project_yaml), "--", "echo", "ok"])

    assert result.exit_code == 0
    assert "all good" in result.output
