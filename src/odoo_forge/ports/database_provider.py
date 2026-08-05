"""Provider-neutral database lifecycle contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from odoo_forge.credentials.types import CredentialHandle
    from odoo_forge.data_artifacts.types import DataArtifactRef
    from odoo_forge.database.types import (
        CleanupReport,
        CreationReceipt,
        DatabaseCreation,
        DatabaseRef,
        DatabaseSpec,
        OperationIdentity,
        RecoveryPoint,
    )


@runtime_checkable
class DatabaseProvider(Protocol):
    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        """Provision using an opaque CredentialHandle; providers never receive plaintext."""
        ...

    def restore(
        self,
        spec: DatabaseSpec,
        artifact: DataArtifactRef,
        credentials: CredentialHandle,
    ) -> DatabaseCreation:
        """Restore a single restore set through an opaque DataArtifactRef.

        Providers receive an opaque CredentialHandle and never plaintext.
        """
        ...

    def adopt(self, ref: DatabaseRef) -> DatabaseRef: ...

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation: ...

    def delete(self, creation: DatabaseCreation) -> None: ...

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport: ...


@runtime_checkable
class DatabaseRecoveryPointCapability(DatabaseProvider, Protocol):
    """Optional provider capability for safe existing-target mutation."""

    def acquire_recovery_point(self, ref: DatabaseRef) -> RecoveryPoint:
        """Acquire an opaque recovery point before mutating an existing target."""
        ...

    def restore_recovery_point(self, ref: DatabaseRef, point: RecoveryPoint) -> None:
        """Restore an opaque recovery point without exposing provider payloads."""
        ...

    def verify_recovery_point(self, ref: DatabaseRef, point: RecoveryPoint) -> bool:
        """Verify the target matches an opaque recovery point after restoration."""
        ...


__all__ = ["DatabaseProvider", "DatabaseRecoveryPointCapability"]
