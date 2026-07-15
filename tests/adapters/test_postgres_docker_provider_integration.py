"""Opt-in real-Docker lifecycle harness for the PostgreSQL database adapter."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

from odoo_forge.credentials import CredentialHandle
from odoo_forge.data_artifacts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DataArtifactRef,
    DiscardOutcome,
    RestoreReadiness,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.database import DatabaseCreation, DatabaseSpec
from odoo_forge.database.errors import (
    CredentialUnavailableError,
    DatabaseOperationError,
    DatabaseReadinessError,
)
from odoo_forge.database.readiness import GateReadinessEvidence, evaluate_gate_readiness
from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority
from odoo_forge_postgres_docker.provider import DockerPostgresqlDatabaseProvider

pytestmark = [pytest.mark.integration, pytest.mark.real_docker]


def _docker(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *argv], capture_output=True, text=True, check=False)


def _require_real_docker() -> None:
    try:
        result = _docker(["info", "--format", "{{.ServerVersion}}"])
    except FileNotFoundError:
        pytest.skip("Docker prerequisite unavailable: executable not found")
    if result.returncode != 0:
        pytest.skip("Docker prerequisite unavailable: daemon is unreachable")


def _container_exists(name: str) -> bool:
    return _docker(["container", "inspect", name]).returncode == 0


def _psql(name: str, *environment: str) -> subprocess.CompletedProcess[str]:
    return _docker(
        ["exec", *environment, name, "psql", "-h", "127.0.0.1", "-U", "postgres", "-c", "select 1"]
    )


def _wait_for_psql(name: str, *environment: str) -> subprocess.CompletedProcess[str]:
    result = _psql(name, *environment)
    for _ in range(60):
        if result.returncode == 0:
            return result
        time.sleep(0.25)
        result = _psql(name, *environment)
    return result


def _container_ip(name: str) -> str:
    result = _docker(
        ["inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name]
    )
    return result.stdout.strip()


def _config_env(name: str) -> list[str]:
    result = _docker(["inspect", "-f", "{{json .Config.Env}}", name])
    env: list[str] = json.loads(result.stdout)
    return env


def _peer_psql(host: str, password: str) -> subprocess.CompletedProcess[str]:
    # A separate container reaches the provisioned database over the bridge by
    # IP, so pg_hba's scram-sha-256 (not the loopback trust rule) is exercised.
    return _docker(
        [
            "run",
            "--rm",
            "-e",
            f"PGPASSWORD={password}",
            "postgres:16",
            "psql",
            "-h",
            host,
            "-U",
            "postgres",
            "-c",
            "select 1",
        ]
    )


def _wait_peer_psql(host: str, password: str) -> subprocess.CompletedProcess[str]:
    result = _peer_psql(host, password)
    for _ in range(40):
        if result.returncode == 0:
            return result
        time.sleep(0.25)
        result = _peer_psql(host, password)
    return result


@contextmanager
def _credential_target(password: str) -> Iterator[str]:
    # The provider now consumes the plaintext secret directly; the injector
    # writes it to the container's POSTGRES_PASSWORD_FILE target.
    yield password


class _ReadyArtifacts:
    def validate_for_restore(self, _ref: DataArtifactRef) -> RestoreReadiness:
        return RestoreReadiness(
            ready=True,
            manifest=RestoreSetManifest(
                restore_set_id="integration-restore",
                lineage_id="integration-lineage",
                components=(
                    RestoreSetComponent(
                        kind=ArtifactComponentKind.DATABASE,
                        opaque_component_ref="database-component",
                        format_version="v1",
                        digest=ArtifactDigest(algorithm="sha256", value="a" * 64),
                    ),
                    RestoreSetComponent(
                        kind=ArtifactComponentKind.FILESTORE,
                        opaque_component_ref="filestore-component",
                        format_version="v1",
                        digest=ArtifactDigest(algorithm="sha256", value="b" * 64),
                    ),
                ),
            ),
            failure_code=None,
            redacted_detail=None,
        )

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        readiness = self.validate_for_restore(ref)
        assert readiness.manifest is not None
        return readiness.manifest

    def discard(self, _ref: DataArtifactRef) -> DiscardOutcome:
        raise NotImplementedError


def test_provision_reconcile_foreign_survival_and_cleanup_against_real_docker() -> None:
    """Prove an owned lifecycle cannot remove an independently created container."""
    _require_real_docker()
    suffix = uuid.uuid4().hex[:12]
    owned_name = f"database-{suffix}"
    foreign_name = f"foreign-{suffix}"
    provider = DockerPostgresqlDatabaseProvider(
        readiness_timeout=30.0, credential_target=lambda _descriptor: _credential_target("existing")
    )
    creation: DatabaseCreation | None = None
    foreign_created = False

    try:
        foreign_result = _docker(["create", "--name", foreign_name, "postgres:16"])
        assert foreign_result.returncode == 0, foreign_result.stderr
        foreign_created = True

        creation = provider.provision(
            DatabaseSpec(name=owned_name), CredentialHandle(f"opaque-{suffix}")
        )
        assert _container_exists(creation.ref.identifier)

        reconciled = DockerPostgresqlDatabaseProvider(readiness_timeout=30.0).reconcile(
            creation.receipt.operation
        )
        assert reconciled.receipt.owned_resource_ids == (owned_name,)

        cleanup = provider.cleanup(creation.receipt)
        assert cleanup.residual_failures == ()
        assert not _container_exists(owned_name)
        assert _container_exists(foreign_name)
        creation = None
    finally:
        if creation is not None:
            cleanup = provider.cleanup(creation.receipt)
            assert cleanup.residual_failures == ()
        if foreign_created:
            result = _docker(["rm", "-f", foreign_name])
            assert result.returncode == 0, result.stderr


def test_runtime_attestation_requires_a_live_ready_docker_container() -> None:
    _require_real_docker()
    name = f"attestation-{uuid.uuid4().hex[:12]}"
    provider = DockerPostgresqlDatabaseProvider(
        readiness_timeout=30.0, credential_target=lambda _descriptor: _credential_target("existing")
    )
    creation: DatabaseCreation | None = None

    try:
        creation = provider.provision(DatabaseSpec(name=name), CredentialHandle("opaque"))
        attestation = provider.verify_runtime_ownership(creation)
        result = evaluate_gate_readiness(
            GateReadinessEvidence(
                approved_proposal_id="proposal-42",
                approved_specification_id="spec-42",
                approved_design_id="design-42",
                verification_receipt_id="verification-42",
                runtime_ownership_evidence=attestation,
            )
        )

        assert result.is_ready is True
        assert name not in repr(attestation)
    finally:
        if creation is not None:
            assert provider.cleanup(creation.receipt).residual_failures == ()


def test_provision_enforces_only_the_injected_secret_as_the_password() -> None:
    """A peer over the bridge proves the injected secret is the enforced password."""
    _require_real_docker()
    name = f"auth-{uuid.uuid4().hex[:12]}"
    password = f"auth-{uuid.uuid4().hex}"
    provider = DockerPostgresqlDatabaseProvider(
        readiness_timeout=30.0, credential_target=lambda _descriptor: _credential_target(password)
    )
    creation: DatabaseCreation | None = None

    try:
        creation = provider.provision(DatabaseSpec(name=name), CredentialHandle("opaque"))
        host = _container_ip(name)
        assert host, "provisioned container must expose a bridge address"
        assert _wait_peer_psql(host, password).returncode == 0
        assert _peer_psql(host, f"wrong-{password}").returncode != 0
    finally:
        if creation is not None:
            assert provider.cleanup(creation.receipt).residual_failures == ()
            assert not _container_exists(name)


def test_provisioned_container_never_exposes_the_plaintext_secret_in_config_env() -> None:
    """Config.Env carries only the POSTGRES_PASSWORD_FILE reference, never the secret."""
    _require_real_docker()
    name = f"secret-{uuid.uuid4().hex[:12]}"
    password = f"secret-{uuid.uuid4().hex}"
    provider = DockerPostgresqlDatabaseProvider(
        readiness_timeout=30.0, credential_target=lambda _descriptor: _credential_target(password)
    )
    creation: DatabaseCreation | None = None

    try:
        creation = provider.provision(DatabaseSpec(name=name), CredentialHandle("opaque"))
        env = _config_env(name)
        assert any(entry.startswith("POSTGRES_PASSWORD_FILE=") for entry in env)
        assert not any(entry.startswith("POSTGRES_PASSWORD=") for entry in env)
        assert all(password not in entry for entry in env)
    finally:
        if creation is not None:
            assert provider.cleanup(creation.receipt).residual_failures == ()
            assert not _container_exists(name)


def test_daemon_restart_reconcile_and_cleanup_survive_on_durable_authority() -> None:
    """Durable signed records let a fresh provider reconcile and clean up after a restart."""
    _require_real_docker()
    name = f"restart-{uuid.uuid4().hex[:12]}"
    password = f"restart-{uuid.uuid4().hex}"
    authority_root = Path(tempfile.mkdtemp(prefix="odoo-forge-authority-"))
    provider = DockerPostgresqlDatabaseProvider(
        readiness_timeout=30.0,
        credential_target=lambda _descriptor: _credential_target(password),
        ownership_authority=LocalOwnershipAuthority(authority_root),
    )
    creation: DatabaseCreation | None = None

    try:
        creation = provider.provision(DatabaseSpec(name=name), CredentialHandle("opaque"))
        # A daemon restart leaves the container present (here simulated as stopped)
        # while the signed authority records persist on disk; the erased secret
        # mount means the container is reconciled and cleaned, never re-run.
        assert _docker(["stop", name]).returncode == 0
        assert _container_exists(name)

        restarted = DockerPostgresqlDatabaseProvider(
            readiness_timeout=30.0,
            ownership_authority=LocalOwnershipAuthority(authority_root),
        )
        reconciled = restarted.reconcile(creation.receipt.operation)
        assert reconciled.receipt.owned_resource_ids == (name,)

        cleanup = restarted.cleanup(reconciled.receipt)
        assert cleanup.residual_failures == ()
        assert not _container_exists(name)
        creation = None
    finally:
        if creation is not None:
            provider.cleanup(creation.receipt)
        shutil.rmtree(authority_root, ignore_errors=True)


def test_forced_readiness_failure_rolls_back_the_real_created_container() -> None:
    _require_real_docker()
    name = f"rollback-{uuid.uuid4().hex[:12]}"
    secret = "integration-readiness-secret"

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(argv, 1, stderr=secret)
        return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout)

    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        readiness_timeout=0.0,
        credential_target=lambda _descriptor: _credential_target("existing"),
    )

    with pytest.raises(DatabaseReadinessError) as excinfo:
        provider.provision(DatabaseSpec(name=name), CredentialHandle("opaque"))

    assert secret not in str(excinfo.value)
    assert not _container_exists(name)


def test_restore_uses_an_opaque_artifact_handoff_and_real_cleanup() -> None:
    _require_real_docker()
    name = f"restore-{uuid.uuid4().hex[:12]}"
    injected: list[RestoreSetComponent] = []

    def restore_target(component: RestoreSetComponent, target: str) -> bool:
        # Loopback is trust in the postgres:16 image, so the injector reaches the
        # database over 127.0.0.1 without carrying any credential of its own.
        injected.append(component)
        if _wait_for_psql(target).returncode != 0:
            return False
        applied = _docker(
            [
                "exec",
                target,
                "psql",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                "-c",
                "create table restored_content (value text); "
                "insert into restored_content values ('restored')",
            ]
        )
        observed = _docker(
            [
                "exec",
                target,
                "psql",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                "-tAc",
                "select value from restored_content",
            ]
        )
        return applied.returncode == 0 and observed.stdout.strip() == "restored"

    provider = DockerPostgresqlDatabaseProvider(
        artifact_capability=_ReadyArtifacts(),
        restore_injector=restore_target,
        readiness_timeout=30.0,
        credential_target=lambda _descriptor: _credential_target("existing"),
    )
    creation: DatabaseCreation | None = None

    try:
        creation = provider.restore(
            DatabaseSpec(name=name),
            DataArtifactRef("opaque-restore-ref"),
            CredentialHandle("opaque"),
        )
        assert injected[0].opaque_component_ref == "database-component"
        assert "bytes" not in repr(injected[0])
        assert _container_exists(creation.ref.identifier)
    finally:
        if creation is not None:
            cleanup = provider.cleanup(creation.receipt)
            assert cleanup.residual_failures == ()
            assert not _container_exists(name)


def test_credential_and_restore_failures_are_redacted_before_docker_mutation() -> None:
    secret = "integration-handoff-secret"

    def credential_injector(_descriptor: object) -> None:
        raise RuntimeError(secret)

    provider = DockerPostgresqlDatabaseProvider(credential_injector=credential_injector)

    with pytest.raises(CredentialUnavailableError) as credentials_error:
        provider.provision(DatabaseSpec(name="redaction-credentials"), CredentialHandle("opaque"))

    assert secret not in str(credentials_error.value)

    def restore_injector(_component: RestoreSetComponent, _target: str) -> bool:
        raise RuntimeError(secret)

    provider = DockerPostgresqlDatabaseProvider(
        artifact_capability=_ReadyArtifacts(),
        credential_target=lambda _descriptor: _credential_target("existing"),
        restore_injector=restore_injector,
        readiness_timeout=30.0,
    )

    with pytest.raises(DatabaseOperationError) as restore_error:
        provider.restore(
            DatabaseSpec(name="redaction-restore"),
            DataArtifactRef("opaque-restore-ref"),
            CredentialHandle("opaque"),
        )

    assert secret not in str(restore_error.value)
