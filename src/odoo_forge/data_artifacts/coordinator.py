"""Durable coordinator driving capture -> anonymize -> deliver as ONE operation.

Realizes design decision D5 (delivery gate) and the coordinator -> `durable_operations`
mapping: `ACCEPTED` -> `IN_PROGRESS` with `DurableCheckpoint`s `captured`, `anonymized`,
`integrity_verified`; on failure, `FAILED` -> `CLEANUP_REQUIRED` -> `DataArtifactCapability.discard`
over the staged capture reference (`CompensationScope`).

Anonymize-by-default is enforced here: raw (non-anonymized) delivery is refused unless a
matching audited `RedactedEvidence(event="anonymization_exception")` grant is found — via the
injected `audited_exception_lookup` port — for the captured manifest's `lineage_id`. This is a
durable audit-trail lookup, never a boolean flag (spec: "Anonymize by Default; Audited Exception
Required for Raw Delivery").

Digest integrity (reconciliation task 0.2) is re-verified via `DataArtifactCapability
.validate_for_restore` immediately before delivery is trusted: a `ValidationFailureCode
.INTEGRITY_FAILED` readiness is surfaced as the concrete `CaptureIntegrityError`, which carries
the failure code as a class attribute; any other non-ready failure code is surfaced as
`CaptureNotReadyError`, which carries the actual `ValidationFailureCode` as an instance
attribute (the enum member itself is never raised as an exception).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from odoo_forge.anonymization.apply import apply_anonymization
from odoo_forge.data_artifacts.contracts import ValidationFailureCode
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import ArtifactUnavailableError
from odoo_forge.durable_operations.service import (
    advance_lifecycle,
    build_terminal_commit,
    ensure_compensation_target,
    save_checkpoint,
)
from odoo_forge.durable_operations.types import (
    CompensationScope,
    LifecycleState,
    OperationRevision,
    RedactedEvidence,
)

if TYPE_CHECKING:
    from odoo_forge.anonymization.apply import MaskTransform
    from odoo_forge.anonymization.policy import AnonymizationPolicy
    from odoo_forge.credentials.types import CredentialHandle
    from odoo_forge.data_artifacts.capture import CaptureSource, DataArtifactCaptureCapability
    from odoo_forge.data_artifacts.contracts import DataArtifactCapability
    from odoo_forge.database.types import DatabaseCreation, DatabaseSpec
    from odoo_forge.durable_operations.service import DurableCheckpoint
    from odoo_forge.durable_operations.types import DurableOperationIdentity
    from odoo_forge.ports.database_provider import DatabaseProvider

AuditedExceptionLookup = Callable[[str], "RedactedEvidence | None"]


class CaptureIntegrityError(ArtifactUnavailableError):
    """Raised when re-verified digest integrity fails before delivery is trusted."""

    public_detail = "capture integrity verification failed"
    failure_code = ValidationFailureCode.INTEGRITY_FAILED


class CaptureNotReadyError(ArtifactUnavailableError):
    """Raised when restore readiness fails for a reason other than integrity."""

    public_detail = "capture failed restore readiness verification"

    def __init__(self, failure_code: ValidationFailureCode) -> None:
        super().__init__()
        self.failure_code = failure_code


class RawDeliveryRefusedError(ArtifactUnavailableError):
    """Raised when raw delivery is requested without a matching audited exception grant."""

    public_detail = "raw delivery refused without an audited anonymization exception"


def _no_audited_exception(_lineage_id: str) -> RedactedEvidence | None:
    return None


@dataclass(frozen=True)
class CoordinatedCopyResult:
    """The successful outcome of one capture -> anonymize -> deliver operation."""

    creation: DatabaseCreation
    checkpoints: tuple[DurableCheckpoint, ...]
    state: LifecycleState


def _is_matching_audited_grant(grant: RedactedEvidence | None, lineage_id: str) -> bool:
    return (
        grant is not None
        and grant.event == "anonymization_exception"
        and lineage_id in grant.references
    )


class DataArtifactCopyCoordinator:
    """Drive one durable capture -> anonymize -> deliver operation."""

    def __init__(
        self,
        *,
        capture_capability: DataArtifactCaptureCapability,
        artifact_capability: DataArtifactCapability,
        database_provider: DatabaseProvider,
        mask_transform: MaskTransform,
        audited_exception_lookup: AuditedExceptionLookup = _no_audited_exception,
    ) -> None:
        self._capture_capability = capture_capability
        self._artifact_capability = artifact_capability
        self._database_provider = database_provider
        self._mask_transform = mask_transform
        self._audited_exception_lookup = audited_exception_lookup
        self.last_state: LifecycleState = LifecycleState.ACCEPTED

    def run(
        self,
        *,
        source: CaptureSource,
        spec: DatabaseSpec,
        policy: AnonymizationPolicy,
        credentials: CredentialHandle,
        operation: DurableOperationIdentity,
        request_raw_delivery: bool = False,
    ) -> CoordinatedCopyResult:
        """Capture, anonymize (or gate raw delivery), verify integrity, then deliver."""
        state, revision = advance_lifecycle(
            LifecycleState.ACCEPTED, OperationRevision(value=0), LifecycleState.IN_PROGRESS
        )
        self.last_state = state
        checkpoints: list[DurableCheckpoint] = []
        ref: DataArtifactRef | None = None
        try:
            captured_manifest = self._capture_capability.capture(source)
            ref = DataArtifactRef(captured_manifest.restore_set_id)
            checkpoints.append(
                save_checkpoint(
                    revision,
                    "captured",
                    RedactedEvidence(
                        event="captured",
                        summary="capture completed",
                        references=(captured_manifest.lineage_id,),
                    ),
                )
            )

            if request_raw_delivery:
                grant = self._audited_exception_lookup(captured_manifest.lineage_id)
                if not _is_matching_audited_grant(grant, captured_manifest.lineage_id):
                    raise RawDeliveryRefusedError()
                assert grant is not None
                anonymize_evidence = grant
            else:
                outcome = apply_anonymization(captured_manifest, policy, self._mask_transform)
                anonymize_evidence = outcome.evidence
            checkpoints.append(save_checkpoint(revision, "anonymized", anonymize_evidence))

            readiness = self._artifact_capability.validate_for_restore(ref)
            if not readiness.ready:
                failure_code = readiness.failure_code
                if failure_code is ValidationFailureCode.INTEGRITY_FAILED:
                    raise CaptureIntegrityError()
                assert failure_code is not None
                raise CaptureNotReadyError(failure_code)
            checkpoints.append(
                save_checkpoint(
                    revision,
                    "integrity_verified",
                    RedactedEvidence(
                        event="integrity_verified",
                        summary="digest re-verified before delivery",
                        references=(captured_manifest.lineage_id,),
                    ),
                )
            )

            creation = self._database_provider.restore(spec, ref, credentials)
            commit = build_terminal_commit(
                expected_revision=revision,
                outcome=LifecycleState.SUCCEEDED,
                evidence=(checkpoints[-1].evidence,),
                residual_cleanup=(),
            )
            self.last_state = commit.outcome
            return CoordinatedCopyResult(
                creation=creation, checkpoints=tuple(checkpoints), state=commit.outcome
            )
        except Exception:
            self._compensate(operation, revision, ref)
            raise

    def _compensate(
        self,
        operation: DurableOperationIdentity,
        revision: OperationRevision,
        ref: DataArtifactRef | None,
    ) -> None:
        """Discard any staged capture reference, then reach `CLEANUP_REQUIRED`."""
        failure_evidence = RedactedEvidence(
            event="capture_copy_failed",
            summary="capture-anonymize-deliver operation failed before completion",
        )
        commit = build_terminal_commit(
            expected_revision=revision,
            outcome=LifecycleState.FAILED,
            evidence=(failure_evidence,),
            residual_cleanup=(),
        )
        cleanup_revision = OperationRevision(value=revision.value + 1)
        state, _ = advance_lifecycle(
            commit.outcome, cleanup_revision, LifecycleState.CLEANUP_REQUIRED
        )
        # Advance observable state to the post-failure terminal state before the
        # best-effort staged-ref discard: a discard failure must never leave
        # `last_state` stale at the pre-failure IN_PROGRESS value nor mask the
        # original error that triggered compensation (CRITICAL fix).
        self.last_state = state
        if ref is not None:
            try:
                scope = CompensationScope(
                    operation_id=operation.operation_id, owned_resource_ids=(ref,)
                )
                owned_ref = ensure_compensation_target(scope, ref)
                self._artifact_capability.discard(DataArtifactRef(owned_ref))
            except Exception:
                pass


__all__ = [
    "AuditedExceptionLookup",
    "CaptureIntegrityError",
    "CaptureNotReadyError",
    "CoordinatedCopyResult",
    "DataArtifactCopyCoordinator",
    "RawDeliveryRefusedError",
]
