"""Opaque CAP-CREDENTIALS and CAP-DATA-ARTIFACTS target handoffs."""

from __future__ import annotations

from odoo_forge.credentials.materialization import materialize_for_target
from odoo_forge.credentials.types import (
    CredentialHandle,
    CredentialInjectionDescriptor,
    TargetContext,
)
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    DataArtifactCapability,
    RestoreSetComponent,
    ValidationFailureCode,
)
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import ArtifactUnavailableError


class RestoreArtifactUnavailableError(ArtifactUnavailableError):
    """The artifact capability could not make the restore reference available."""


class RestoreArtifactIncoherentError(ArtifactUnavailableError):
    """The artifact capability rejected an incoherent restore reference."""


class RestoreArtifactIntegrityError(ArtifactUnavailableError):
    """The artifact capability rejected an integrity-invalid restore reference."""


def materialize_database_credentials(handle: CredentialHandle) -> CredentialInjectionDescriptor:
    """Materialize an opaque reference for the database target, never a secret value."""
    target = TargetContext(kind="database", target_id="postgres-docker")
    return materialize_for_target(handle, target)


def validated_database_restore(
    artifact: DataArtifactRef, capability: DataArtifactCapability
) -> RestoreSetComponent:
    """Return the validated database component or raise a redacted typed failure."""
    readiness = capability.validate_for_restore(artifact)
    if not readiness.ready:
        _raise_restore_failure(readiness.failure_code)
    assert readiness.manifest is not None
    return next(
        component
        for component in readiness.manifest.components
        if component.kind is ArtifactComponentKind.DATABASE
    )


def _raise_restore_failure(code: ValidationFailureCode | None) -> None:
    if code is ValidationFailureCode.COHERENCE_FAILED:
        raise RestoreArtifactIncoherentError()
    if code is ValidationFailureCode.INTEGRITY_FAILED:
        raise RestoreArtifactIntegrityError()
    raise RestoreArtifactUnavailableError()


__all__ = [
    "RestoreArtifactIncoherentError",
    "RestoreArtifactIntegrityError",
    "RestoreArtifactUnavailableError",
    "materialize_database_credentials",
    "validated_database_restore",
]
