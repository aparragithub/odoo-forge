"""Safety contracts for the isolated Docker PostgreSQL adapter."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from inspect import getsource
from pathlib import Path
from typing import get_type_hints

import pytest

import odoo_forge_postgres_docker.provider as provider_module
from odoo_forge.credentials.types import CredentialHandle, CredentialInjectionDescriptor
from odoo_forge.data_artifacts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DataArtifactRef,
    DiscardOutcome,
    RestoreReadiness,
    RestoreSetComponent,
    RestoreSetManifest,
    ValidationFailureCode,
)
from odoo_forge.database import CreationReceipt, DatabaseRef, OperationIdentity, ResourceOwnership
from odoo_forge.database.errors import (
    CredentialUnavailableError,
    DatabaseOperationError,
    DatabaseReadinessError,
    OwnershipRefusedError,
)
from odoo_forge.database.readiness import GateReadinessEvidence, evaluate_gate_readiness
from odoo_forge.database.types import DatabaseCreation, DatabaseSpec
from odoo_forge.ports.database_provider import DatabaseProvider
from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority
from odoo_forge_postgres_docker.provider import (
    DockerCommandFailedError,
    DockerCommandTimeoutError,
    DockerPostgresqlDatabaseProvider,
    RollbackIncompleteError,
)
from odoo_forge_postgres_docker.secret_injection import (
    PostgreSQLSecretInjector,
    SecretInjectionError,
)
from odoo_forge_postgres_docker.target_handoffs import (
    RestoreArtifactIncoherentError,
    RestoreArtifactIntegrityError,
    RestoreArtifactUnavailableError,
    materialize_database_credentials,
    validated_database_restore,
)

_OWNED_LABELS = (
    '{"io.odoo-forge.provider":"postgres-docker",'
    '"io.odoo-forge.operation":"postgres-docker:token-42",'
    '"io.odoo-forge.resource-kind":"container",'
    '"io.odoo-forge.creator-token":"token-42"}'
)
_OWNED_INSPECT = '[{"Id":"immutable-database-42","Config":{"Labels":' + _OWNED_LABELS + "}}]"


def _credential_target(
    _descriptor: CredentialInjectionDescriptor,
) -> AbstractContextManager[str]:
    return nullcontext("postgres-password")


def _restore_manifest() -> RestoreSetManifest:
    digest = ArtifactDigest(algorithm="sha256", value="a" * 64)
    return RestoreSetManifest(
        restore_set_id="restore-set-42",
        lineage_id="lineage-42",
        components=(
            RestoreSetComponent(
                kind=ArtifactComponentKind.DATABASE,
                opaque_component_ref="database-component-42",
                format_version="v1",
                digest=digest,
            ),
            RestoreSetComponent(
                kind=ArtifactComponentKind.FILESTORE,
                opaque_component_ref="filestore-component-42",
                format_version="v1",
                digest=digest,
            ),
        ),
    )


class _Artifacts:
    def __init__(self, readiness: RestoreReadiness) -> None:
        self._readiness = readiness
        self.refs: list[DataArtifactRef] = []

    def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness:
        self.refs.append(ref)
        return self._readiness

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        self.refs.append(ref)
        if self._readiness.manifest is None:
            raise RuntimeError("restore reference is unavailable")
        return self._readiness.manifest

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        raise NotImplementedError


def _append_component(
    components: list[RestoreSetComponent], component: RestoreSetComponent
) -> bool:
    components.append(component)
    return True


def _append_restore(
    applied: list[tuple[str, str]], component: RestoreSetComponent, target: str
) -> bool:
    applied.append((component.opaque_component_ref, target))
    return True


def test_target_handoffs_materialize_only_an_opaque_credential_descriptor() -> None:
    descriptor = materialize_database_credentials(CredentialHandle("postgres-password"))

    assert descriptor.store_ref == "sops://postgres-password"
    assert descriptor.target_kind == "database"
    assert "plaintext" not in repr(descriptor)


def test_target_handoffs_pass_only_the_database_component_reference_to_restore_injector() -> None:
    artifacts = _Artifacts(
        RestoreReadiness(
            ready=True,
            manifest=_restore_manifest(),
            failure_code=None,
            redacted_detail=None,
        )
    )
    artifact = DataArtifactRef("restore-set-42")

    component = validated_database_restore(artifact, artifacts)

    assert artifacts.refs == [artifact]
    assert component.opaque_component_ref == "database-component-42"
    assert "restore bytes" not in repr(component)


@pytest.mark.parametrize(
    ("failure_code", "error_type"),
    [
        (ValidationFailureCode.UNAVAILABLE, RestoreArtifactUnavailableError),
        (ValidationFailureCode.COHERENCE_FAILED, RestoreArtifactIncoherentError),
        (ValidationFailureCode.INTEGRITY_FAILED, RestoreArtifactIntegrityError),
    ],
)
def test_restore_validation_fails_closed_without_docker_mutation(
    failure_code: ValidationFailureCode, error_type: type[DatabaseOperationError]
) -> None:
    artifacts = _Artifacts(
        RestoreReadiness(
            ready=False,
            manifest=None,
            failure_code=failure_code,
            redacted_detail="artifact validation failed",
        )
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        artifact_capability=artifacts,
    )

    with pytest.raises(error_type) as excinfo:
        provider.restore(
            DatabaseSpec(name="database-42"),
            DataArtifactRef("restore-set-42"),
            CredentialHandle("super-secret"),
        )

    assert calls == []
    assert "super-secret" not in str(excinfo.value)


def test_restore_injects_validated_opaque_handoffs_before_provisioning() -> None:
    calls: list[tuple[str, ...]] = []
    descriptors: list[CredentialInjectionDescriptor] = []
    components: list[RestoreSetComponent] = []
    artifacts = _Artifacts(
        RestoreReadiness(
            ready=True,
            manifest=_restore_manifest(),
            failure_code=None,
            redacted_detail=None,
        )
    )

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        artifact_capability=artifacts,
        credential_injector=descriptors.append,
        credential_target=_credential_target,
        restore_injector=lambda component, _target: _append_component(components, component),
    ).restore(
        DatabaseSpec(name="database-42"),
        DataArtifactRef("restore-set-42"),
        CredentialHandle("postgres-password"),
    )

    assert creation.ref.identifier == "database-42"
    assert descriptors[0].store_ref == "sops://postgres-password"
    assert components[0].opaque_component_ref == "database-component-42"
    assert calls[0][:3] == ("docker", "run", "--detach")


def test_credential_target_injector_failure_is_typed_and_redacted() -> None:
    secret = "credential-injector-super-secret"

    def credential_injector(_descriptor: CredentialInjectionDescriptor) -> None:
        raise RuntimeError(f"credential injection failed: {secret}")

    provider = DockerPostgresqlDatabaseProvider(credential_injector=credential_injector)

    with pytest.raises(CredentialUnavailableError) as excinfo:
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert str(excinfo.value) == "database credentials are unavailable"
    assert secret not in str(excinfo.value)


def test_provision_passes_only_a_protected_credential_target_file_reference_to_docker(
    tmp_path: Path,
) -> None:
    secret = "credential-target-secret"
    calls: list[tuple[str, ...]] = []

    @contextmanager
    def credential_target(descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        assert descriptor.store_ref == "sops://opaque"
        yield secret

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", credential_target=credential_target
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert creation.ref.identifier == "database-42"
    assert "--env-file" not in calls[0]
    assert "POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password" in calls[0]
    assert any(item.startswith("type=bind,src=") for item in calls[0])
    assert secret not in " ".join(item for call in calls for item in call)
    assert secret not in repr(creation)
    assert list(tmp_path.iterdir()) == []


def test_provision_preserves_a_ready_container_when_secret_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "cleanup-failure-secret"
    calls: list[tuple[str, ...]] = []

    @contextmanager
    def credential_target(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield secret

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def failing_erase(_secret_path: object, _directory: object) -> None:
        raise SecretInjectionError()

    monkeypatch.setattr(PostgreSQLSecretInjector, "_erase", staticmethod(failing_erase))

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", credential_target=credential_target
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert creation.ref.identifier == "database-42"
    assert not any(call[:3] == ("docker", "rm", "-f") for call in calls)


def test_provision_survives_a_directory_fsync_failure_after_the_state_commit(
    tmp_path: Path,
) -> None:
    secret = "fsync-after-commit-secret"
    calls: list[tuple[str, ...]] = []

    @contextmanager
    def credential_target(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield secret

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    class FsyncFailingAuthority(LocalOwnershipAuthority):
        def _fsync_directory(self) -> None:
            raise OSError("directory fsync failed after commit")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        credential_target=credential_target,
        ownership_authority=FsyncFailingAuthority(tmp_path / "authority"),
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert creation.ref.identifier == "database-42"
    assert not any(call[:3] == ("docker", "rm", "-f") for call in calls)


def test_restore_target_injector_failure_is_typed_and_redacted() -> None:
    secret = "restore-artifact-super-secret"
    artifacts = _Artifacts(
        RestoreReadiness(
            ready=True,
            manifest=_restore_manifest(),
            failure_code=None,
            redacted_detail=None,
        )
    )

    def restore_injector(_component: RestoreSetComponent, _target: str) -> bool:
        raise RuntimeError(f"restore injection failed: {secret}")

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        artifact_capability=artifacts,
        credential_target=_credential_target,
        restore_injector=restore_injector,
    )

    with pytest.raises(DatabaseOperationError) as excinfo:
        provider.restore(
            DatabaseSpec(name="database-42"),
            DataArtifactRef("restore-set-42"),
            CredentialHandle("opaque"),
        )

    assert str(excinfo.value) == "database provider operation failed"
    assert secret not in str(excinfo.value)


def test_restore_applies_and_verifies_the_validated_component_at_the_live_target() -> None:
    calls: list[tuple[str, ...]] = []
    applied: list[tuple[str, str]] = []
    artifacts = _Artifacts(
        RestoreReadiness(
            ready=True, manifest=_restore_manifest(), failure_code=None, redacted_detail=None
        )
    )

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        artifact_capability=artifacts,
        credential_target=_credential_target,
        restore_injector=lambda component, target: _append_restore(applied, component, target),
    ).restore(
        DatabaseSpec(name="database-42"), DataArtifactRef("restore-set-42"), CredentialHandle("x")
    )

    assert applied == [("database-component-42", creation.ref.identifier)]
    assert calls[0][:3] == ("docker", "run", "--detach")


def test_runtime_attestation_is_minted_only_after_live_ownership_and_readiness_checks(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(
        {
            "operation": "postgres-docker:token-42",
            "kind": "container",
            "name": "database-42",
            "docker_id": "immutable-database-42",
            "state": "active",
        }
    )
    provider = DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", ownership_authority=authority
    )
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token-42"),
            owned_resource_ids=("database-42",),
        ),
    )

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

    assert calls == [
        ("docker", "inspect", "database-42"),
        ("docker", "exec", "database-42", "pg_isready", "-U", "postgres"),
    ]
    assert result.is_ready is True
    assert "database-42" not in repr(attestation)
    assert "token-42" not in repr(attestation)


@pytest.mark.parametrize(
    "inspection",
    [
        '[{"Config":{"Labels":{}}}]',
        '[{"Config":{"Labels":{"io.odoo-forge.provider":"postgres-docker",'
        '"io.odoo-forge.operation":"postgres-docker:forged",'
        '"io.odoo-forge.resource-kind":"container",'
        '"io.odoo-forge.creator-token":"forged"}}}]',
    ],
)
def test_runtime_attestation_refuses_forged_live_labels(inspection: str) -> None:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, inspection, "")

    provider = DockerPostgresqlDatabaseProvider(runner=runner, token_factory=lambda: "token-42")
    forged_creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token-42"),
            owned_resource_ids=("database-42",),
        ),
    )

    with pytest.raises(OwnershipRefusedError):
        provider.verify_runtime_ownership(forged_creation)


def test_runtime_attestation_refuses_a_forged_receipt_membership() -> None:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")

    provider = DockerPostgresqlDatabaseProvider(runner=runner, token_factory=lambda: "token-42")
    forged_creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token-42"),
            owned_resource_ids=("other-database",),
        ),
    )

    with pytest.raises(OwnershipRefusedError):
        provider.verify_runtime_ownership(forged_creation)


def test_runtime_attestation_refuses_labels_and_readiness_without_authority(tmp_path: Path) -> None:
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token-42"),
            owned_resource_ids=("database-42",),
        ),
    )
    provider = DockerPostgresqlDatabaseProvider(
        runner=lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, ""),
        ownership_authority=LocalOwnershipAuthority(tmp_path / "authority"),
    )

    with pytest.raises(OwnershipRefusedError):
        provider.verify_runtime_ownership(creation)


def test_run_timeout_recovers_live_authorized_container_and_retires_it(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argv, timeout)
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        credential_target=_credential_target,
        ownership_authority=authority,
    )

    with pytest.raises(DockerCommandTimeoutError):
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert authority.read()["records"][-1]["state"] == "retired"


def test_retry_retires_active_authority_when_prior_removal_left_no_container(
    tmp_path: Path,
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    authority.write(
        {
            "operation": receipt.operation.value,
            "kind": "container",
            "name": "database-42",
            "docker_id": "immutable-database-42",
            "state": "active",
        }
    )

    provider = DockerPostgresqlDatabaseProvider(
        runner=lambda argv, *, timeout: subprocess.CompletedProcess(
            argv, 1, "", "Error: No such object: database-42"
        ),
        ownership_authority=authority,
    )

    assert provider.cleanup(receipt).residual_failures == ()
    assert authority.read()["records"][-1]["state"] == "retired"


def test_cleanup_accepts_visible_retirement_after_directory_fsync_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    authority.reserve(receipt.operation.value, "database-42")
    authority.bind(receipt.operation.value, "database-42", "immutable-database-42")
    authority.activate(receipt.operation.value, "database-42", "immutable-database-42")
    monkeypatch.setattr(authority, "_fsync_directory", lambda: (_ for _ in ()).throw(OSError()))

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "inspect"] and len(argv) == 3:
            if authority.read()["records"][-1]["state"] == "retired":
                return subprocess.CompletedProcess(argv, 1, "", "No such object")
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    assert (
        DockerPostgresqlDatabaseProvider(runner=runner, ownership_authority=authority)
        .cleanup(receipt)
        .residual_failures
        == ()
    )


@pytest.mark.parametrize("failure_after_run", [False, True])
def test_failed_rollback_returns_a_reconciliation_handle(
    failure_after_run: bool,
) -> None:
    calls: list[tuple[str, ...]] = []
    inspections = 0

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        nonlocal inspections
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            inspections += 1
            return subprocess.CompletedProcess(
                argv, 1 if failure_after_run and inspections > 1 else 0, _OWNED_INSPECT, ""
            )
        if argv[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(argv, 1, "", "not ready")
        if argv[:3] == ["docker", "rm", "-f"] and not failure_after_run:
            return subprocess.CompletedProcess(argv, 1, "", "removal failed")
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        readiness_timeout=0,
        credential_target=_credential_target,
    )
    with pytest.raises(RollbackIncompleteError) as excinfo:
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("x"))

    assert excinfo.value.receipt.owned_resource_ids == ("database-42",)
    assert excinfo.value.residual_failures == ("database-42",)
    assert "x" not in str(excinfo.value)
    assert excinfo.value.__cause__ is not excinfo.value


def test_hostile_resource_name_is_rejected_before_subprocess_execution() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(runner=runner)

    with pytest.raises(DatabaseOperationError) as excinfo:
        provider.inspect_resource("db; touch /tmp/pwned")

    assert str(excinfo.value) == "database provider operation failed"
    assert calls == []


def test_safe_resource_name_is_passed_as_a_single_argv_argument() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    result = DockerPostgresqlDatabaseProvider(runner=runner).inspect_resource("safe-db")

    assert result.stdout == "[]"
    assert calls == [("docker", "inspect", "safe-db")]


@pytest.mark.parametrize(
    ("runner", "error_type"),
    [
        (
            lambda _argv, *, timeout: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(["docker"], timeout)
            ),
            DockerCommandTimeoutError,
        ),
        (
            lambda argv, *, timeout: subprocess.CompletedProcess(
                argv, 1, "", "fatal: password=super-secret"
            ),
            DockerCommandFailedError,
        ),
    ],
)
def test_docker_failures_are_typed_and_redacted(
    runner: object, error_type: type[DatabaseOperationError]
) -> None:
    provider = DockerPostgresqlDatabaseProvider(runner=runner)  # type: ignore[arg-type]

    with pytest.raises(error_type) as excinfo:
        provider.inspect_resource("safe-db")

    assert str(excinfo.value) == "database provider operation failed"
    assert "super-secret" not in str(excinfo.value)


def test_mismatched_live_labels_refuse_mutation() -> None:
    provider = DockerPostgresqlDatabaseProvider()
    receipt = provider.creation_receipt("safe-db")
    labels = provider.labels_for(receipt.operation, resource_kind="container")
    labels["io.odoo-forge.creator-token"] = "forged-token"

    with pytest.raises(OwnershipRefusedError) as excinfo:
        provider.assert_live_ownership(receipt, "safe-db", labels, resource_kind="container")

    assert str(excinfo.value) == "database resource ownership does not permit this operation"


def test_matching_live_labels_and_receipt_membership_prove_ownership() -> None:
    provider = DockerPostgresqlDatabaseProvider()
    receipt = provider.creation_receipt("safe-db")

    provider.assert_live_ownership(
        receipt,
        "safe-db",
        provider.labels_for(receipt.operation, resource_kind="container"),
        resource_kind="container",
    )


def test_adapter_conforms_to_database_provider_protocol_without_docker_import() -> None:
    provider = DockerPostgresqlDatabaseProvider()

    assert isinstance(provider, DatabaseProvider)
    assert "odoo_forge_docker" not in provider.__class__.__module__


def test_adapter_preserves_database_provider_type_contracts() -> None:
    provision_hints = get_type_hints(DockerPostgresqlDatabaseProvider.provision)
    restore_hints = get_type_hints(DockerPostgresqlDatabaseProvider.restore)

    assert provision_hints == {
        "spec": DatabaseSpec,
        "credentials": CredentialHandle,
        "return": DatabaseCreation,
    }
    assert restore_hints["artifact"] is DataArtifactRef
    assert restore_hints["credentials"] is CredentialHandle


def test_adapter_source_stays_isolated_from_local_backend_routing() -> None:
    source = getsource(provider_module)

    assert "odoo_forge_docker" not in source
    assert "DockerBackendProvider" not in source
    assert "odoo_forge_cli" not in source


def test_provision_creates_only_receipted_container_then_proves_bounded_readiness() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:3] == ["docker", "inspect", "database-42"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    tokens = iter(["token-42"])
    provider = DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: next(tokens), credential_target=_credential_target
    )

    creation = provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert creation.ref == DatabaseRef(
        identifier="database-42", ownership=ResourceOwnership.CREATED
    )
    assert creation.receipt.owned_resource_ids == ("database-42",)
    assert calls[0][:3] == ("docker", "run", "--detach")
    assert ("docker", "exec", "database-42", "pg_isready", "-U", "postgres") in calls


def test_provision_reserves_before_docker_then_binds_and_activates(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "run"]:
            records = authority.read()["records"]
            assert records[-1]["state"] == "reserved"
            assert records[-1]["docker_id"] == ""
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        credential_target=_credential_target,
        ownership_authority=authority,
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    records = authority.read()["records"]
    assert [record["state"] for record in records] == ["reserved", "reserved", "active"]
    assert records[-1]["docker_id"] == "immutable-database-42"
    assert creation.ref.identifier == "database-42"
    assert calls[0][:2] == ("docker", "run")


def test_pre_docker_authority_failure_is_typed_redacted_and_never_runs_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fail_reserve(_operation: str, _name: str) -> None:
        raise RuntimeError("authority password=super-secret")

    monkeypatch.setattr(authority, "reserve", fail_reserve)
    provider = DockerPostgresqlDatabaseProvider(
        runner=runner, credential_target=_credential_target, ownership_authority=authority
    )

    with pytest.raises(DatabaseOperationError) as excinfo:
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert str(excinfo.value) == "database provider operation failed"
    assert "super-secret" not in str(excinfo.value)
    assert calls == []


def test_cleanup_retires_verified_authority_and_lost_authority_refuses_mutation(
    tmp_path: Path,
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    authority.reserve(receipt.operation.value, "database-42")
    authority.bind(receipt.operation.value, "database-42", "immutable-database-42")
    authority.activate(receipt.operation.value, "database-42", "immutable-database-42")
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")

    provider = DockerPostgresqlDatabaseProvider(runner=runner, ownership_authority=authority)
    assert provider.cleanup(receipt).residual_failures == ()
    assert authority.read()["records"][-1]["state"] == "retired"

    with pytest.raises(OwnershipRefusedError):
        provider.delete(
            DatabaseCreation(
                ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
                receipt=receipt,
            )
        )
    assert calls.count(("docker", "rm", "-f", "database-42")) == 1


@pytest.mark.parametrize("resource_id", ["db; touch /tmp/pwned", "database-42 $(id)"])
def test_lifecycle_rejects_shell_injected_ids_before_docker(resource_id: str) -> None:
    calls: list[tuple[str, ...]] = []
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=(resource_id,),
    )

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(runner=runner)

    with pytest.raises(DatabaseOperationError):
        provider.cleanup(receipt)

    assert calls == []


def test_unsupported_docker_runtime_is_typed_and_redacted() -> None:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker 19 unsupported password=super-secret")

    with pytest.raises(DockerCommandFailedError) as excinfo:
        DockerPostgresqlDatabaseProvider(runner=runner).inspect_resource("database-42")

    assert str(excinfo.value) == "database provider operation failed"
    assert "super-secret" not in str(excinfo.value)


def test_successful_default_provision_persists_its_immutable_docker_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", credential_target=_credential_target
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority

    state = LocalOwnershipAuthority(tmp_path / "odoo-forge" / "postgres-docker").read()
    assert state["records"][-1]["operation"] == creation.receipt.operation.value
    assert state["records"][-1]["name"] == creation.ref.identifier
    assert state["records"][-1]["docker_id"] == "immutable-database-42"


def test_delete_refuses_same_name_replacement_with_copied_labels(tmp_path: Path) -> None:
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority

    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(
        {
            "operation": receipt.operation.value,
            "kind": "container",
            "name": "database-42",
            "docker_id": "original-immutable-id",
            "state": "active",
        }
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(OwnershipRefusedError):
        DockerPostgresqlDatabaseProvider(runner=runner, ownership_authority=authority).delete(
            DatabaseCreation(
                ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
                receipt=receipt,
            )
        )

    assert ("docker", "rm", "-f", "database-42") not in calls


def test_provision_extracts_labels_from_a_docker_inspect_container_array() -> None:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                _OWNED_INSPECT,
                "",
            )
        return subprocess.CompletedProcess(argv, 0, "", "")

    creation = DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", credential_target=_credential_target
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert creation.ref.identifier == "database-42"


@pytest.mark.parametrize("stdout", ["not-json password=secret", "[]", "{}", "[{}]"])
def test_inspect_labels_refuses_malformed_empty_or_wrong_shaped_output(stdout: str) -> None:
    provider = DockerPostgresqlDatabaseProvider(
        runner=lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, stdout, "")
    )

    with pytest.raises(OwnershipRefusedError) as excinfo:
        provider._inspect_labels("database-42")

    assert str(excinfo.value) == "database resource ownership does not permit this operation"
    assert "secret" not in str(excinfo.value)


def test_provision_fails_with_typed_unavailable_outcome_when_readiness_bound_expires() -> None:
    ticks = iter([0.0, 0.0, 2.0])

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        if argv[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(argv, 1, "", "not ready password=secret")
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        readiness_timeout=1.0,
        monotonic=lambda: next(ticks),
        sleep=lambda _seconds: None,
        credential_target=_credential_target,
    )

    with pytest.raises(DatabaseReadinessError) as excinfo:
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert str(excinfo.value) == "database resource is not ready"
    assert "secret" not in str(excinfo.value)


def test_partial_provision_failure_rolls_back_created_resources_in_reverse_order() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:3] == ["docker", "exec", "database-42"]:
            return subprocess.CompletedProcess(argv, 1, "", "not ready")
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    ticks = iter([0.0, 2.0])
    provider = DockerPostgresqlDatabaseProvider(
        runner=runner,
        token_factory=lambda: "token-42",
        readiness_timeout=1.0,
        monotonic=lambda: next(ticks),
        sleep=lambda _seconds: None,
        credential_target=_credential_target,
    )

    with pytest.raises(DatabaseReadinessError):
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert calls[-1] == ("docker", "rm", "-f", "database-42")


def test_reconcile_refuses_to_rebuild_a_created_receipt_from_matching_live_labels(
    tmp_path: Path,
) -> None:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(argv, 0, "database-42\n", "")
        return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")

    with pytest.raises(OwnershipRefusedError):
        DockerPostgresqlDatabaseProvider(
            runner=runner,
            ownership_authority=LocalOwnershipAuthority(tmp_path / "authority"),
        ).reconcile(OperationIdentity(value="postgres-docker:token-42"))


def test_delete_and_cleanup_require_local_authority_and_refuse_foreign_resources(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42", "database-43"),
    )

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"] and argv[-1] == "database-43":
            return subprocess.CompletedProcess(argv, 0, '{"io.odoo-forge.provider":"external"}', "")
        return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")

    from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority

    authority = LocalOwnershipAuthority(tmp_path / "authority")
    for resource_id in receipt.owned_resource_ids:
        authority.write(
            {
                "operation": receipt.operation.value,
                "kind": "container",
                "name": resource_id,
                "docker_id": f"immutable-{resource_id}",
                "state": "active",
            }
        )
    unproven = DockerPostgresqlDatabaseProvider(runner=runner)
    foreign = DatabaseCreation(
        ref=DatabaseRef(identifier="database-43", ownership=ResourceOwnership.CREATED),
        receipt=receipt,
    )
    with pytest.raises(OwnershipRefusedError):
        unproven.delete(foreign)
    assert ("docker", "rm", "-f", "database-43") not in calls

    provider = DockerPostgresqlDatabaseProvider(runner=runner, ownership_authority=authority)
    with pytest.raises(OwnershipRefusedError):
        provider.delete(foreign)

    report = provider.cleanup(receipt)

    assert report.residual_failures == ("database-43",)
    assert ("docker", "rm", "-f", "database-42") in calls
    assert ("docker", "rm", "-f", "database-43") not in calls


def test_cleanup_reports_zero_residuals_after_all_locally_owned_resources_are_removed(
    tmp_path: Path,
) -> None:
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority

    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(
        {
            "operation": receipt.operation.value,
            "kind": "container",
            "name": "database-42",
            "docker_id": "immutable-database-42",
            "state": "active",
        }
    )
    report = DockerPostgresqlDatabaseProvider(
        runner=lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, ""),
        ownership_authority=authority,
    ).cleanup(receipt)

    assert report.residual_failures == ()


def test_destructive_delete_refuses_a_created_reference_missing_from_its_receipt() -> None:
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-43", ownership=ResourceOwnership.CREATED),
        receipt=receipt,
    )

    with pytest.raises(OwnershipRefusedError) as excinfo:
        DockerPostgresqlDatabaseProvider().delete(creation)

    assert str(excinfo.value) == "database resource ownership does not permit this operation"


def test_adopt_preserves_an_external_reference_without_mutation() -> None:
    external = DatabaseRef(identifier="database-42", ownership=ResourceOwnership.EXTERNAL)

    adopted = DockerPostgresqlDatabaseProvider().adopt(external)

    assert adopted == external


# -- characterization: baseline name-only spec + `-U postgres` probe --
#
# Pins the CURRENT `_provision`/`_wait_ready` argv (name-only `DatabaseSpec`,
# no network/volume/env/labels tokens; readiness probe always uses
# `-U postgres` with no `-d`) before Phase 1/2 widen `DatabaseSpec` with
# additive topology fields and Phase 2.3 derives the probe from `spec.env`.


def test_current_database_spec_accepts_only_name_with_no_topology_fields() -> None:
    """Pins the pre-Phase-1 `DatabaseSpec` shape: `name` only."""
    spec = DatabaseSpec(name="database-42")

    assert spec.model_dump() == {"name": "database-42"}


def test_current_provision_argv_carries_no_network_volume_or_label_topology_tokens() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", credential_target=_credential_target
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    run_call = calls[0]
    assert run_call[:5] == ("docker", "run", "--detach", "--name", "database-42")
    assert "--network" not in run_call
    assert "-v" not in run_call
    assert "-e" not in run_call


def test_current_wait_ready_probe_always_uses_dash_u_postgres_with_no_dash_d() -> None:
    """Pins the pre-Phase-2.3 readiness probe: always `-U postgres`, never a
    `-d <database>` token, regardless of any caller-side database name."""
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if argv[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    DockerPostgresqlDatabaseProvider(
        runner=runner, token_factory=lambda: "token-42", credential_target=_credential_target
    ).provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    exec_call = next(call for call in calls if call[:2] == ("docker", "exec"))
    assert exec_call == ("docker", "exec", "database-42", "pg_isready", "-U", "postgres")
    assert "-d" not in exec_call
