"""Safety contracts for the isolated Docker PostgreSQL adapter."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from inspect import getsource
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
from odoo_forge.database.types import DatabaseCreation, DatabaseSpec
from odoo_forge.ports.database_provider import DatabaseProvider
from odoo_forge_postgres_docker.provider import (
    DockerCommandFailedError,
    DockerCommandTimeoutError,
    DockerPostgresqlDatabaseProvider,
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
_OWNED_INSPECT = '[{"Config":{"Labels":' + _OWNED_LABELS + '}}]'


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
        restore_injector=components.append,
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

    def restore_injector(_component: RestoreSetComponent) -> None:
        raise RuntimeError(f"restore injection failed: {secret}")

    provider = DockerPostgresqlDatabaseProvider(
        artifact_capability=artifacts,
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
    provider = DockerPostgresqlDatabaseProvider(runner=runner, token_factory=lambda: next(tokens))

    creation = provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert creation.ref == DatabaseRef(
        identifier="database-42", ownership=ResourceOwnership.CREATED
    )
    assert creation.receipt.owned_resource_ids == ("database-42",)
    assert calls[0][:3] == ("docker", "run", "--detach")
    assert ("docker", "exec", "database-42", "pg_isready", "-U", "postgres") in calls


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
        runner=runner, token_factory=lambda: "token-42"
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
    )

    with pytest.raises(DatabaseReadinessError):
        provider.provision(DatabaseSpec(name="database-42"), CredentialHandle("opaque"))

    assert calls[-1] == ("docker", "rm", "-f", "database-42")


def test_reconcile_rebuilds_a_created_receipt_from_matching_live_labels() -> None:
    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(argv, 0, "database-42\n", "")
        return subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")

    creation = DockerPostgresqlDatabaseProvider(runner=runner).reconcile(
        OperationIdentity(value="postgres-docker:token-42")
    )

    assert creation.ref.identifier == "database-42"
    assert creation.receipt.owned_resource_ids == ("database-42",)


def test_delete_and_cleanup_refuse_foreign_resources_and_remove_all_owned_resources() -> None:
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

    provider = DockerPostgresqlDatabaseProvider(runner=runner)
    foreign = DatabaseCreation(
        ref=DatabaseRef(identifier="database-43", ownership=ResourceOwnership.CREATED),
        receipt=receipt,
    )
    with pytest.raises(OwnershipRefusedError):
        provider.delete(foreign)

    report = provider.cleanup(receipt)

    assert report.residual_failures == ("database-43",)
    assert ("docker", "rm", "-f", "database-42") in calls
    assert ("docker", "rm", "-f", "database-43") not in calls


def test_cleanup_reports_zero_residuals_after_all_receipt_owned_resources_are_removed() -> None:
    receipt = CreationReceipt(
        operation=OperationIdentity(value="postgres-docker:token-42"),
        owned_resource_ids=("database-42",),
    )
    report = DockerPostgresqlDatabaseProvider(
        runner=lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, _OWNED_INSPECT, "")
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
