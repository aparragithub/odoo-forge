"""Fail-closed orchestration for one policy-governed data-environment copy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_artifacts.coordinator import CoordinatedCopyResult, DataArtifactCopyCoordinator
from odoo_forge.data_environments.types import (
    DataEnvironmentDefinition,
    EnvironmentFailureCode,
    EnvironmentLifecycle,
    EnvironmentOperationOutcome,
    EnvironmentOutcomeCode,
    RawDataGrant,
)
from odoo_forge.database.types import DatabaseRef, DatabaseSpec, RecoveryPoint
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.types import InstancePointer, InstanceRecord
from odoo_forge.ports.data_environment_registry import DataEnvironmentRegistry
from odoo_forge.ports.database_provider import DatabaseRecoveryPointCapability
from odoo_forge.ports.instance_registry import InstanceRegistry
from odoo_forge.ports.raw_data_grant_authority import RawDataGrantAuthority

PolicyResolver = Callable[[str], AnonymizationPolicy]
OperationVerifier = Callable[[CoordinatedCopyResult], bool]


class _PreflightFailure(Exception):
    def __init__(
        self,
        code: EnvironmentFailureCode,
        policy: str | None = None,
        raw_grant: RawDataGrant | None = None,
    ):
        self.code, self.policy, self.raw_grant = code, policy, raw_grant


class _RecoveryFailure(Exception):
    def __init__(self, code: EnvironmentFailureCode):
        self.code = code


class DataEnvironmentOperationRequest:
    def __init__(
        self,
        *,
        operation: DurableOperationIdentity,
        source_environment_id: str,
        target_environment_id: str,
        target_pointer: InstancePointer,
        target_ref: DatabaseRef | None,
        source: CaptureSource,
        spec: DatabaseSpec,
        credentials: CredentialHandle,
        actor: str,
        intent: str,
        request_raw_delivery: bool = False,
    ) -> None:
        self.operation = operation
        self.source_environment_id = source_environment_id
        self.target_environment_id = target_environment_id
        self.target_pointer = target_pointer
        self.target_ref = target_ref
        self.source = source
        self.spec = spec
        self.credentials = credentials
        self.actor, self.intent = actor, intent
        self.request_raw_delivery = request_raw_delivery


@dataclass(frozen=True)
class DataEnvironmentLineage:
    actor: str
    intent: str
    source: str
    target: str
    policy: str | None
    recovery_point: RecoveryPoint | None
    raw_grant: RawDataGrant | None = None


@dataclass(frozen=True)
class DataEnvironmentOperationResult:
    outcome: EnvironmentOperationOutcome
    lineage: DataEnvironmentLineage
    copy_result: CoordinatedCopyResult | None = None


class DataEnvironmentService:
    """Run preflight completely before delegating to the accepted copy workflow."""

    def __init__(
        self,
        *,
        environment_registry: DataEnvironmentRegistry,
        instance_registry: InstanceRegistry,
        raw_grant_authority: RawDataGrantAuthority,
        database_provider: DatabaseRecoveryPointCapability,
        coordinator: DataArtifactCopyCoordinator,
        policy_resolver: PolicyResolver,
        verify_operation: OperationVerifier = lambda result: True,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._environments = environment_registry
        self._instances = instance_registry
        self._grants = raw_grant_authority
        self._provider = database_provider
        self._coordinator = coordinator
        self._policy = policy_resolver
        self._verify_operation = verify_operation
        self._now = now

    def run(self, request: DataEnvironmentOperationRequest) -> DataEnvironmentOperationResult:
        try:
            definition, _record, policy, grant, point = self._preflight(request)
        except _PreflightFailure as failure:
            return self._result(
                request,
                EnvironmentOutcomeCode.REFUSED,
                failure.code,
                failure.policy,
                raw_grant=failure.raw_grant,
            )

        try:
            copy_result = self._coordinator.run(
                source=request.source,
                spec=request.spec,
                policy=policy,
                credentials=request.credentials,
                operation=request.operation,
                request_raw_delivery=request.request_raw_delivery,
                raw_grant=grant,
            )
        except Exception:
            return self._after_mutation_failure(
                request,
                point,
                EnvironmentFailureCode.MUTATION_FAILED,
                definition.policy_ref,
                grant,
            )
        if not self._verify_operation(copy_result):
            return self._after_mutation_failure(
                request,
                point,
                EnvironmentFailureCode.OPERATION_VERIFICATION_FAILED,
                definition.policy_ref,
                grant,
            )
        return DataEnvironmentOperationResult(
            outcome=EnvironmentOperationOutcome(code=EnvironmentOutcomeCode.SUCCEEDED),
            lineage=self._lineage(request, definition.policy_ref, point, grant),
            copy_result=copy_result,
        )

    def _preflight(
        self, request: DataEnvironmentOperationRequest
    ) -> tuple[
        DataEnvironmentDefinition,
        InstanceRecord,
        AnonymizationPolicy,
        RawDataGrant | None,
        RecoveryPoint | None,
    ]:
        try:
            definition = self._environments.resolve(request.target_environment_id)
        except Exception as exc:
            raise _PreflightFailure(EnvironmentFailureCode.AUTHORITY_UNAVAILABLE) from exc
        if (
            definition.environment_id != request.target_environment_id
            or definition.lifecycle is not EnvironmentLifecycle.ACTIVE
            or definition.scope != request.target_pointer.scope
            or not any(
                r.source_environment_id == request.source_environment_id
                and r.target_environment_id == request.target_environment_id
                for r in definition.relationships
            )
            or request.source.target.target_id != request.source_environment_id
        ):
            raise _PreflightFailure(
                EnvironmentFailureCode.INVALID_DEFINITION, definition.policy_ref
            )
        try:
            record = self._instances.get(request.target_pointer)
        except Exception as exc:
            raise _PreflightFailure(
                EnvironmentFailureCode.AUTHORITY_UNAVAILABLE, definition.policy_ref
            ) from exc
        if record.receipt is None or record.resource.identifier != (
            request.target_ref.identifier if request.target_ref else record.resource.identifier
        ):
            raise _PreflightFailure(
                EnvironmentFailureCode.INVALID_DEFINITION, definition.policy_ref
            )
        try:
            policy = self._policy(definition.policy_ref)
            if not isinstance(policy, AnonymizationPolicy):
                raise TypeError("policy resolver returned an invalid policy")
        except Exception as exc:
            raise _PreflightFailure(
                EnvironmentFailureCode.INVALID_DEFINITION, definition.policy_ref
            ) from exc
        grant = None
        if request.request_raw_delivery:
            try:
                grant = self._grants.authorize(
                    request.operation.operation_id, definition.environment_id
                )
            except Exception as exc:
                raise _PreflightFailure(
                    EnvironmentFailureCode.RAW_GRANT_REQUIRED, definition.policy_ref
                ) from exc
            if (
                grant is None
                or grant.operation_id != request.operation.operation_id
                or (
                    grant.environment_id != definition.environment_id
                    or grant.expires_at <= self._now()
                )
            ):
                raise _PreflightFailure(
                    EnvironmentFailureCode.RAW_GRANT_REQUIRED, definition.policy_ref
                )
        point = None
        if request.target_ref is not None:
            try:
                point = self._provider.acquire_recovery_point(request.target_ref)
            except Exception as exc:
                raise _PreflightFailure(
                    EnvironmentFailureCode.RECOVERY_POINT_UNAVAILABLE,
                    definition.policy_ref,
                    grant,
                ) from exc
            if not isinstance(point, RecoveryPoint):
                raise _PreflightFailure(
                    EnvironmentFailureCode.RECOVERY_POINT_UNAVAILABLE,
                    definition.policy_ref,
                    grant,
                )
        return definition, record, policy, grant, point

    def _after_mutation_failure(
        self,
        request: DataEnvironmentOperationRequest,
        point: RecoveryPoint | None,
        failure_code: EnvironmentFailureCode,
        policy: str,
        raw_grant: RawDataGrant | None = None,
    ) -> DataEnvironmentOperationResult:
        if point is not None:
            target_ref = request.target_ref
            assert target_ref is not None
            try:
                self._provider.restore_recovery_point(target_ref, point)
            except Exception:
                return self._result(
                    request,
                    EnvironmentOutcomeCode.FAILED,
                    EnvironmentFailureCode.RECOVERY_RESTORE_FAILED,
                    policy,
                    point,
                    raw_grant,
                )
            try:
                if not self._provider.verify_recovery_point(target_ref, point):
                    raise _RecoveryFailure(EnvironmentFailureCode.RECOVERY_VERIFICATION_FAILED)
            except _RecoveryFailure as failure:
                return self._result(
                    request,
                    EnvironmentOutcomeCode.FAILED,
                    failure.code,
                    policy,
                    point,
                    raw_grant,
                )
            except Exception:
                return self._result(
                    request,
                    EnvironmentOutcomeCode.FAILED,
                    EnvironmentFailureCode.RECOVERY_VERIFICATION_FAILED,
                    policy,
                    point,
                    raw_grant,
                )
        return self._result(
            request,
            EnvironmentOutcomeCode.FAILED,
            failure_code,
            policy,
            point,
            raw_grant,
        )

    def _result(
        self,
        request: DataEnvironmentOperationRequest,
        code: EnvironmentOutcomeCode,
        failure: EnvironmentFailureCode,
        policy: str | None = None,
        point: RecoveryPoint | None = None,
        raw_grant: RawDataGrant | None = None,
    ) -> DataEnvironmentOperationResult:
        return DataEnvironmentOperationResult(
            outcome=EnvironmentOperationOutcome(code=code, failure_code=failure),
            lineage=self._lineage(request, policy, point, raw_grant),
        )

    @staticmethod
    def _lineage(
        request: DataEnvironmentOperationRequest,
        policy: str | None,
        point: RecoveryPoint | None,
        raw_grant: RawDataGrant | None = None,
    ) -> DataEnvironmentLineage:
        return DataEnvironmentLineage(
            actor=request.actor,
            intent=request.intent,
            source=request.source_environment_id,
            target=request.target_environment_id,
            policy=policy,
            recovery_point=point,
            raw_grant=raw_grant,
        )


__all__ = [
    "DataEnvironmentLineage",
    "DataEnvironmentOperationRequest",
    "DataEnvironmentOperationResult",
    "DataEnvironmentService",
]
