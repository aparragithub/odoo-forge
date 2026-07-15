"""Opt-in real-Docker lifecycle harness for the PostgreSQL database adapter."""

from __future__ import annotations

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
    for _ in range(30):
        result = _psql(name, *environment)
        if result.returncode == 0:
            return result
        time.sleep(0.1)
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


def test_provision_requires_the_authorized_credential_target_handoff() -> None:
    """PostgreSQL rejects missing/wrong passwords but accepts the target credential."""
    _require_real_docker()
    name = f"auth-{uuid.uuid4().hex[:12]}"
    password = f"auth-{uuid.uuid4().hex}"
    provider = DockerPostgresqlDatabaseProvider(
        readiness_timeout=30.0, credential_target=lambda _descriptor: _credential_target(password)
    )
    creation: DatabaseCreation | None = None
    pgpass = Path(tempfile.mkstemp(prefix="odoo-forge-pgpass-")[1])

    try:
        pgpass.write_text(f"127.0.0.1:5432:*:postgres:{password}\n")
        pgpass.chmod(0o600)
        creation = provider.provision(DatabaseSpec(name=name), CredentialHandle("opaque"))
        assert _psql(name).returncode != 0
        assert _psql(name, "-e", "PGPASSWORD=wrong").returncode != 0
        assert _docker(["cp", str(pgpass), f"{name}:/tmp/pgpass"]).returncode == 0
        assert _wait_for_psql(name, "-e", "PGPASSFILE=/tmp/pgpass").returncode == 0
    finally:
        pgpass.unlink(missing_ok=True)
        if creation is not None:
            assert provider.cleanup(creation.receipt).residual_failures == ()
            assert not _container_exists(name)


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
    pgpass = Path(tempfile.mkstemp(prefix="odoo-forge-pgpass-")[1])
    pgpass.write_text("127.0.0.1:5432:*:postgres:existing\n")
    pgpass.chmod(0o600)

    def restore_target(component: RestoreSetComponent, target: str) -> bool:
        injected.append(component)
        copied = _docker(["cp", str(pgpass), f"{target}:/tmp/pgpass"])
        if (
            copied.returncode != 0
            or _wait_for_psql(target, "-e", "PGPASSFILE=/tmp/pgpass").returncode != 0
        ):
            return False
        applied = _docker(
            [
                "exec",
                "-e",
                "PGPASSFILE=/tmp/pgpass",
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
                "-e",
                "PGPASSFILE=/tmp/pgpass",
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
        pgpass.unlink(missing_ok=True)
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
