from __future__ import annotations

import inspect
import typing

import pytest

from odoo_forge.credentials import CredentialHandle
from odoo_forge.data_artifacts import DataArtifactRef
from odoo_forge.database import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
    OperationIdentity,
    ResourceOwnership,
)
from odoo_forge.database.errors import IncompleteCleanupError, OwnershipRefusedError
from odoo_forge.ports.database_provider import DatabaseProvider


def _creation() -> DatabaseCreation:
    return DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="provision-42"),
            owned_resource_ids=("database-42",),
        ),
    )


class _ConformingDatabaseProvider:
    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        return _creation()

    def restore(
        self,
        spec: DatabaseSpec,
        artifact: DataArtifactRef,
        credentials: CredentialHandle,
    ) -> DatabaseCreation:
        return _creation()

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        return _creation()

    def delete(self, creation: DatabaseCreation) -> None:
        return None

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        return CleanupReport()


class _MissingCleanupProvider:
    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        return _creation()

    def restore(
        self,
        spec: DatabaseSpec,
        artifact: DataArtifactRef,
        credentials: CredentialHandle,
    ) -> DatabaseCreation:
        return _creation()

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        return _creation()

    def delete(self, creation: DatabaseCreation) -> None:
        return None


class _IncompatibleSignatureProvider:
    def provision(self, spec: DatabaseSpec) -> DatabaseCreation:
        return _creation()

    def restore(
        self,
        spec: DatabaseSpec,
        artifact: DataArtifactRef,
        credentials: CredentialHandle,
    ) -> DatabaseCreation:
        return _creation()

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        return _creation()

    def delete(self, creation: DatabaseCreation) -> None:
        return None

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        return CleanupReport()


class _OwnershipSafeDatabaseProvider:
    def __init__(self) -> None:
        self.deleted_resource_ids: list[str] = []

    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        return _creation()

    def restore(
        self,
        spec: DatabaseSpec,
        artifact: DataArtifactRef,
        credentials: CredentialHandle,
    ) -> DatabaseCreation:
        return _creation()

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        return _creation()

    def delete(self, creation: DatabaseCreation) -> None:
        if (
            creation.ref.ownership is not ResourceOwnership.CREATED
            or creation.ref.identifier not in creation.receipt.owned_resource_ids
        ):
            raise OwnershipRefusedError("creator proof is unavailable")
        self.deleted_resource_ids.append(creation.ref.identifier)

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        if receipt.operation.value not in {"created-42", "cleanup-failure-42"}:
            raise OwnershipRefusedError("creator proof is unavailable")
        if receipt.operation.value == "cleanup-failure-42":
            return CleanupReport(residual_failures=("cleanup-failure-42",))
        return CleanupReport()


def test_conforming_provider_satisfies_the_runtime_protocol() -> None:
    provider = _ConformingDatabaseProvider()

    assert isinstance(provider, DatabaseProvider)
    assert provider.reconcile(OperationIdentity(value="retry-42")) == _creation()
    assert provider.cleanup(_creation().receipt) == CleanupReport()


def test_provider_missing_a_lifecycle_operation_is_rejected() -> None:
    assert not isinstance(_MissingCleanupProvider(), DatabaseProvider)


def test_runtime_protocol_accepts_but_signature_inspection_rejects_incompatible_method() -> None:
    port_signature = inspect.signature(DatabaseProvider.provision)
    incompatible_signature = inspect.signature(_IncompatibleSignatureProvider.provision)

    assert isinstance(_IncompatibleSignatureProvider(), DatabaseProvider)
    assert list(port_signature.parameters) == ["self", "spec", "credentials"]
    assert list(incompatible_signature.parameters) == ["self", "spec"]
    assert port_signature != incompatible_signature


def test_receipt_owned_creation_is_deleted_with_creator_proof() -> None:
    provider = _OwnershipSafeDatabaseProvider()
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="created-42"),
            owned_resource_ids=("database-42",),
        ),
    )

    provider.delete(creation)

    assert provider.deleted_resource_ids == ["database-42"]


@pytest.mark.parametrize("ownership", [ResourceOwnership.ADOPTED, ResourceOwnership.EXTERNAL])
def test_adopted_or_external_resources_refuse_destructive_actions(
    ownership: ResourceOwnership,
) -> None:
    provider = _OwnershipSafeDatabaseProvider()
    creation = DatabaseCreation(
        ref=DatabaseRef(identifier="database-42", ownership=ownership),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="created-42"),
            owned_resource_ids=("database-42",),
        ),
    )

    with pytest.raises(OwnershipRefusedError):
        provider.delete(creation)
    with pytest.raises(OwnershipRefusedError):
        provider.cleanup(
            CreationReceipt(
                operation=OperationIdentity(value="adopted-42"),
                owned_resource_ids=("database-42",),
            )
        )

    assert provider.deleted_resource_ids == []


def test_cleanup_reports_a_safe_residual_and_uses_a_typed_redacted_failure() -> None:
    provider = _OwnershipSafeDatabaseProvider()
    report = provider.cleanup(
        CreationReceipt(
            operation=OperationIdentity(value="cleanup-failure-42"),
            owned_resource_ids=("database-42",),
        )
    )
    error = IncompleteCleanupError("credential_secret=secret-sentinel")

    assert report.residual_failures == ("cleanup-failure-42",)
    assert isinstance(error, IncompleteCleanupError)
    assert "secret-sentinel" not in str(error)


def test_lifecycle_method_signatures_match_the_contract() -> None:
    localns = {
        "CleanupReport": CleanupReport,
        "CreationReceipt": CreationReceipt,
        "CredentialHandle": CredentialHandle,
        "DataArtifactRef": DataArtifactRef,
        "DatabaseCreation": DatabaseCreation,
        "DatabaseRef": DatabaseRef,
        "DatabaseSpec": DatabaseSpec,
        "OperationIdentity": OperationIdentity,
    }

    for name in ("provision", "restore", "adopt", "reconcile", "delete", "cleanup"):
        port_method = getattr(DatabaseProvider, name)
        implementation_method = getattr(_ConformingDatabaseProvider, name)
        port_signature = inspect.signature(port_method)
        implementation_signature = inspect.signature(implementation_method)

        assert list(port_signature.parameters) == list(implementation_signature.parameters)
        assert all(
            parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            for parameter in list(port_signature.parameters.values())[1:]
        )
        assert all(
            parameter.default is inspect.Parameter.empty
            for parameter in list(port_signature.parameters.values())[1:]
        )

        port_hints = typing.get_type_hints(port_method, localns=localns)
        implementation_hints = typing.get_type_hints(implementation_method)
        for parameter in list(port_signature.parameters)[1:]:
            assert port_hints[parameter] == implementation_hints[parameter]
        assert port_hints["return"] == implementation_hints["return"]
