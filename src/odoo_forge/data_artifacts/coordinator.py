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

Bridge slice B4 (design D11/D12) adds two consistency/GC behaviors on top of the above,
without changing `DataArtifactCapability`'s signature or the ref-based
`validate_for_restore(ref)`/`restore(spec, ref, ...)` calls:

- **D11 (anonymize-re-store consistency)**: when the non-raw path masks the captured manifest
  via `apply_anonymization`, the resulting (possibly digest-changed) manifest is re-persisted
  under the SAME `ref` through the injected `manifest_persistence` port BEFORE
  `validate_for_restore(ref)` runs. `manifest_persistence` stays an OPTIONAL constructor
  argument (default a no-op), so a caller may still omit it — but the coordinator no longer
  trusts that re-persistence actually happened. Instead, it is FAIL-CLOSED by an internal
  consistency check (CRITICAL fix, no signature change): `validate_for_restore(ref)` already
  returns the manifest the store now resolves for `ref` (`RestoreReadiness.manifest`). Right
  before delivery, the coordinator compares that served manifest's DATABASE component digest
  against the masked manifest's DATABASE component digest. With a real (digest-changing) mask
  and a no-op/unwired `manifest_persistence`, the store still serves the RAW digest, the
  comparison fails, and an `AnonymizationConsistencyError` is raised before delivery — the
  anonymization bypass this no-op default previously permitted is blocked at the boundary
  instead of at construction time. With an identity mask (masked digest == raw digest, e.g. the
  pre-existing `test_coordinator.py` fakes) the comparison trivially holds either way. A real
  caller still wires `manifest_persistence` to the same `StagedArtifactStore.put` the
  `DataArtifactCapability`/mask transform already share, so the served manifest is
  byte-consistent BY CONSTRUCTION and the check is a no-op safety net, not the primary path.
- **Raw pre-mask blob reap (CRITICAL fix)**: re-persisting the masked manifest under the SAME
  `ref` supersedes the raw manifest that named the pre-mask (unmasked PII) blob; because the
  store is content-addressed and `discard` only ever inspects the CURRENT manifest at a ref, the
  raw blob is never found again and lingers on disk forever. The coordinator closes this gap
  without any new store API: only when masking actually changed the database component's
  digest, it persists the RAW manifest under a throwaway shadow ref BEFORE overwriting `ref`
  with the masked manifest, then discards the shadow ref (an identity/pass-through mask skips
  this entirely — there is nothing to reap, and it keeps `artifact_capability.discard` call
  counts unchanged for identity-mask callers such as `test_coordinator.py`'s fakes). `discard` is
  dedup-aware (it only unlinks a component's blob when no OTHER staged manifest still references
  that digest), so once `ref` holds the masked manifest, a component whose digest is unchanged by
  masking (e.g. filestore, or the whole database component under a pass-through v1 mask) is still
  "referenced elsewhere" via `ref` and is preserved, while a component whose digest actually
  changed is no longer referenced by ANY manifest under its raw digest and is safely reaped.
  The shadow-ref persist-then-discard sequence is wrapped in `try`/`finally`: once the shadow
  manifest is persisted, its discard is GUARANTEED even if the intervening re-persist of `ref`
  with the masked manifest raises — otherwise a fault between the two `manifest_persistence`
  calls would leave the shadow manifest (and its raw, unmasked-PII blob) permanently leaked
  while the original error still propagates. A non-raising `DiscardOutcomeCode.RESIDUAL_FAILURE`
  or a raised exception from that shadow-ref discard is recorded as a durable
  `raw_reap_residual` checkpoint (CRITICAL fix) rather than silently swallowed, mirroring D12
  below.
- **D12 (discard-on-success GC)**: after delivery SUCCEEDS, the coordinator best-effort discards
  the staged capture reference (`DataArtifactCapability.discard`) — the staged dump is redundant
  once the target database holds the data, and durable audit already lives in the
  `durable_operations` checkpoints/evidence, never in the bytes themselves. `retain_staged=True`
  opts out. A non-raising `DiscardOutcomeCode.RESIDUAL_FAILURE` OR a raised discard exception is
  recorded as a durable checkpoint/evidence rather than silently dropped (WARNING fix). The
  pre-existing on-failure `_compensate` discard is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from odoo_forge.anonymization.apply import apply_anonymization
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DiscardOutcomeCode,
    RestoreSetManifest,
    ValidationFailureCode,
)
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
    from odoo_forge.data_environments.types import RawDataGrant
    from odoo_forge.database.types import DatabaseCreation, DatabaseSpec
    from odoo_forge.durable_operations.service import DurableCheckpoint
    from odoo_forge.durable_operations.types import DurableOperationIdentity
    from odoo_forge.ports.database_provider import DatabaseProvider

AuditedExceptionLookup = Callable[[str], "RedactedEvidence | None"]
ManifestPersistence = Callable[[DataArtifactRef, RestoreSetManifest], None]


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


class AnonymizationConsistencyError(ArtifactUnavailableError):
    """Raised fail-closed when the manifest the store now resolves for `ref` does not match
    the masked manifest anonymization produced (D11 anonymize-re-store consistency guard)."""

    public_detail = "anonymized manifest is not consistent with the manifest the store resolves"


def _no_audited_exception(_lineage_id: str) -> RedactedEvidence | None:
    return None


def _no_manifest_persistence(_ref: DataArtifactRef, _manifest: RestoreSetManifest) -> None:
    """Default no-op `ManifestPersistence`: callers may omit real re-persistence, since the
    D11 consistency check below fails closed instead of trusting it happened."""
    return None


def _database_digest(manifest: RestoreSetManifest) -> ArtifactDigest | None:
    return next(
        (
            component.digest
            for component in manifest.components
            if component.kind is ArtifactComponentKind.DATABASE
        ),
        None,
    )


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
        manifest_persistence: ManifestPersistence = _no_manifest_persistence,
        audited_exception_lookup: AuditedExceptionLookup = _no_audited_exception,
    ) -> None:
        self._capture_capability = capture_capability
        self._artifact_capability = artifact_capability
        self._database_provider = database_provider
        self._mask_transform = mask_transform
        self._audited_exception_lookup = audited_exception_lookup
        self._manifest_persistence = manifest_persistence
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
        retain_staged: bool = False,
        raw_grant: RawDataGrant | None = None,
        raw_grant_environment_id: str | None = None,
    ) -> CoordinatedCopyResult:
        """Capture, anonymize (or gate raw delivery), verify integrity, then deliver."""
        state, revision = advance_lifecycle(
            LifecycleState.ACCEPTED, OperationRevision(value=0), LifecycleState.IN_PROGRESS
        )
        self.last_state = state
        checkpoints: list[DurableCheckpoint] = []
        ref: DataArtifactRef | None = None
        masked_manifest: RestoreSetManifest | None = None
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
                if raw_grant is not None and (
                    raw_grant.operation_id != operation.operation_id
                    or raw_grant.environment_id != raw_grant_environment_id
                    or raw_grant.expires_at <= datetime.now(UTC)
                ):
                    raise RawDeliveryRefusedError()
                grant = (
                    RedactedEvidence(
                        event="anonymization_exception",
                        summary="approved raw-data exception",
                        references=(captured_manifest.lineage_id, str(raw_grant.audit_reference)),
                    )
                    if raw_grant is not None
                    else self._audited_exception_lookup(captured_manifest.lineage_id)
                )
                if not _is_matching_audited_grant(grant, captured_manifest.lineage_id):
                    raise RawDeliveryRefusedError()
                assert grant is not None
                anonymize_evidence = grant
            else:
                outcome = apply_anonymization(captured_manifest, policy, self._mask_transform)
                anonymize_evidence = outcome.evidence
                masked_manifest = outcome.manifest
                if _database_digest(masked_manifest) != _database_digest(captured_manifest):
                    # Persist the RAW manifest under a throwaway shadow ref BEFORE overwriting
                    # `ref` with the masked manifest (CRITICAL fix: see module docstring "Raw
                    # pre-mask blob reap"). This ordering matters: only once `ref` already holds
                    # the masked manifest does an unchanged component (e.g. filestore) count as
                    # "referenced elsewhere" and survive the shadow-ref discard below. Skipped
                    # entirely when masking left the database digest unchanged (identity/
                    # pass-through mask): there is nothing to reap, and this also keeps a
                    # `manifest_persistence`-agnostic `artifact_capability.discard` call count
                    # unchanged for identity-mask callers.
                    shadow_ref = DataArtifactRef(
                        f"{captured_manifest.restore_set_id}-preanonymize-raw"
                    )
                    self._manifest_persistence(shadow_ref, captured_manifest)
                    # Once the shadow manifest is persisted above, it must NEVER leak: the
                    # `finally` guarantees the shadow ref is always reaped even if the
                    # intervening re-persist of `ref` below raises (CRITICAL fix: a fault
                    # between the two `manifest_persistence` calls used to leave the shadow
                    # manifest — and therefore its raw, unmasked-PII blob — permanently
                    # dangling in the store).
                    try:
                        # D11: re-persist the (possibly digest-changed) masked manifest under
                        # the SAME ref BEFORE integrity is re-verified, so
                        # `validate_for_restore`/`restore` resolve bytes that match the
                        # anonymized manifest by construction.
                        self._manifest_persistence(ref, outcome.manifest)
                    finally:
                        # Reap the shadow ref: dedup-aware `discard` unlinks the raw pre-mask
                        # blob only when no other staged manifest (i.e. `ref`, now masked)
                        # still references its digest, so shared/unchanged components are
                        # preserved. Best-effort — a reap failure must never mask the
                        # original error (if any) that triggered this `finally`. But a
                        # failed reap leaves the raw (unmasked PII) blob on disk, so a
                        # RESIDUAL_FAILURE outcome or a raised exception is recorded as a
                        # durable checkpoint (CRITICAL fix), mirroring the D12
                        # discard-on-success residual recording below.
                        try:
                            raw_reap_outcome = self._artifact_capability.discard(shadow_ref)
                        except Exception:
                            raw_reap_residual = True
                        else:
                            raw_reap_residual = (
                                raw_reap_outcome.code is DiscardOutcomeCode.RESIDUAL_FAILURE
                            )
                        if raw_reap_residual:
                            checkpoints.append(
                                save_checkpoint(
                                    revision,
                                    "raw_reap_residual",
                                    RedactedEvidence(
                                        event="raw_reap_residual",
                                        summary="raw pre-mask blob reap left a residual failure",
                                        references=(captured_manifest.lineage_id,),
                                    ),
                                )
                            )
                else:
                    self._manifest_persistence(ref, outcome.manifest)
            checkpoints.append(save_checkpoint(revision, "anonymized", anonymize_evidence))

            readiness = self._artifact_capability.validate_for_restore(ref)
            if not readiness.ready:
                failure_code = readiness.failure_code
                if failure_code is ValidationFailureCode.INTEGRITY_FAILED:
                    raise CaptureIntegrityError()
                assert failure_code is not None
                raise CaptureNotReadyError(failure_code)
            if masked_manifest is not None:
                # D11 fail-closed guard: `manifest_persistence` is optional and its default
                # is a no-op, so re-persistence is never trusted blindly. `readiness.manifest`
                # is what the store ACTUALLY resolves for `ref` right now; if it does not carry
                # the masked digest, either re-persistence never happened or something else
                # served stale bytes — either way, delivery must be refused.
                served_digest = (
                    _database_digest(readiness.manifest) if readiness.manifest is not None else None
                )
                masked_digest = _database_digest(masked_manifest)
                if served_digest is None or masked_digest is None or served_digest != masked_digest:
                    raise AnonymizationConsistencyError()
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
            if not retain_staged:
                # D12: discard-on-success GC. Best-effort — a discard failure here must
                # never turn a SUCCEEDED delivery into a reported failure; durable audit
                # already lives in the checkpoints/evidence above, never in the bytes.
                assert ref is not None  # capture() always sets ref before this point
                discard_outcome = None
                discard_raised = False
                try:
                    discard_outcome = self._artifact_capability.discard(ref)
                except Exception:
                    discard_raised = True
                if discard_raised or (
                    discard_outcome is not None
                    and discard_outcome.code is DiscardOutcomeCode.RESIDUAL_FAILURE
                ):
                    # WARNING fix: neither a non-raising RESIDUAL_FAILURE NOR a raised
                    # discard exception may be silently dropped — record it as durable
                    # checkpoint/evidence, consistent with this module's evidence-based
                    # observability (no logging library).
                    checkpoints.append(
                        save_checkpoint(
                            revision,
                            "discard_on_success_residual",
                            RedactedEvidence(
                                event="discard_on_success_residual",
                                summary="discard-on-success left a residual failure",
                                references=(captured_manifest.lineage_id,),
                            ),
                        )
                    )
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
    "AnonymizationConsistencyError",
    "AuditedExceptionLookup",
    "CaptureIntegrityError",
    "CaptureNotReadyError",
    "CoordinatedCopyResult",
    "DataArtifactCopyCoordinator",
    "ManifestPersistence",
    "RawDeliveryRefusedError",
]
