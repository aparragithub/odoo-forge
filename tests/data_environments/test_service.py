# ruff: noqa: E501,E701,E702,I001
# mypy: ignore-errors

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.data_environments.service import (
    DataEnvironmentLineage,
    DataEnvironmentOperationRequest,
    DataEnvironmentService,
)
from odoo_forge.data_environments.types import (
    DataEnvironmentDefinition,
    EnvironmentFailureCode,
    EnvironmentLifecycle,
    EnvironmentOutcomeCode,
    EnvironmentRelationship,
    RawDataGrant,
)
from odoo_forge.database.types import DatabaseRef, DatabaseSpec, RecoveryPoint
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.instance_registry.types import InstanceId, InstancePointer, InstanceRecord
from odoo_forge.resource_ownership import OwnershipReceipt
from odoo_forge.resource_ownership.types import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId

SCOPE = ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1")
POINTER = InstancePointer(scope=SCOPE, instance_id=InstanceId(value="qa"))
OPERATION = DurableOperationIdentity(operation_id="refresh-42", request_digest="request-42")
TARGET = DatabaseRef(identifier="odoo-qa", ownership=ResourceOwnership.CREATED)
DEFINITION = DataEnvironmentDefinition(
    environment_id="qa",
    owner="platform",
    scope=SCOPE,
    lifecycle=EnvironmentLifecycle.ACTIVE,
    policy_ref="policy-qa",
    relationships=(
        EnvironmentRelationship(source_environment_id="production", target_environment_id="qa"),
    ),
)
GRANT = RawDataGrant(
    operation_id="refresh-42",
    environment_id="qa",
    grantor="operator-1",
    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    reason="approved refresh",
    audit_reference="audit-42",
)
DEFAULT_POINT = RecoveryPoint("point-42")


class Registry:
    def __init__(self, events: list[str], definition=DEFINITION):
        self.events, self.definition = events, definition

    def resolve(self, environment_id: str):
        self.events.append("resolve")
        return self.definition


class Instances:
    def __init__(self, events: list[str], record):
        self.events, self.record = events, record

    def get(self, pointer):
        self.events.append("instance")
        return self.record


class Grants:
    def __init__(self, events: list[str], grant):
        self.events, self.grant = events, grant

    def authorize(self, operation_id: str, environment_id: str):
        self.events.append("grant")
        return self.grant


class Provider:
    def __init__(self, events: list[str], restore_error=None, verified=True, point=DEFAULT_POINT):
        self.events, self.restore_error, self.verified, self.point = (
            events,
            restore_error,
            verified,
            point,
        )

    def acquire_recovery_point(self, ref):
        self.events.append("acquire")
        return self.point

    def restore_recovery_point(self, ref, point):
        self.events.append("restore")
        if self.restore_error:
            raise self.restore_error

    def verify_recovery_point(self, ref, point):
        self.events.append("safe-state")
        return self.verified


class Coordinator:
    def __init__(self, events: list[str], error=None):
        self.events, self.error = events, error

    def run(self, **kwargs: Any):
        self.events.append("copy")
        if self.error:
            raise self.error
        return SimpleNamespace(creation="creation-42")


RECORD = InstanceRecord(
    pointer=POINTER,
    resource=ResourceRef(
        identifier="odoo-qa", resource_kind="container", ownership=ResourceOwnership.CREATED
    ),
    receipt=OwnershipReceipt(operation=OPERATION, owned_resource_ids=("container-42",)),
)


def request(raw=False):
    return DataEnvironmentOperationRequest(
        operation=OPERATION,
        source_environment_id="production",
        target_environment_id="qa",
        target_pointer=POINTER,
        target_ref=TARGET,
        source=CaptureSource(
            credentials=CredentialHandle("source"),
            target=TargetContext(kind="source", target_id="production"),
        ),
        spec=DatabaseSpec(name="odoo-qa"),
        credentials=CredentialHandle("target"),
        actor="operator-1",
        intent="refresh",
        request_raw_delivery=raw,
    )


def service(
    events,
    *,
    grant=GRANT,
    coordinator=None,
    provider=None,
    definition=DEFINITION,
    record=RECORD,
    verify_operation=lambda result: True,
    policy_resolver=None,
):
    return DataEnvironmentService(
        environment_registry=Registry(events, definition),
        instance_registry=Instances(events, record),
        raw_grant_authority=Grants(events, grant),
        database_provider=provider or Provider(events),
        coordinator=coordinator or Coordinator(events),
        policy_resolver=policy_resolver
        or (lambda ref: events.append("policy") or AnonymizationPolicy()),
        verify_operation=verify_operation,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_all_preflight_authorities_run_before_copy():
    events: list[str] = []
    result = service(events).run(request(raw=True))
    assert result.outcome.code is EnvironmentOutcomeCode.SUCCEEDED
    assert events == ["resolve", "instance", "policy", "grant", "acquire", "copy"]
    assert result.lineage.raw_grant == GRANT


def test_success_preserves_actor_intent_and_lineage_evidence():
    result = service([]).run(request())
    assert result.lineage == DataEnvironmentLineage(
        actor="operator-1",
        intent="refresh",
        source="production",
        target="qa",
        policy="policy-qa",
        recovery_point=RecoveryPoint("point-42"),
    )


def test_accepted_instance_refusal_precedes_policy_and_mutation():
    events: list[str] = []
    result = service(events, record=RECORD.model_copy(update={"receipt": None})).run(request())
    assert result.outcome.failure_code is EnvironmentFailureCode.INVALID_DEFINITION
    assert events == ["resolve", "instance"]


def test_invalid_policy_refuses_before_grant_and_mutation():
    events: list[str] = []
    result = service(events, policy_resolver=lambda ref: object()).run(request(raw=True))
    assert result.outcome.failure_code is EnvironmentFailureCode.INVALID_DEFINITION
    assert events == ["resolve", "instance"]


@pytest.mark.parametrize(
    "grant",
    [
        GRANT.model_copy(update={"expires_at": datetime(2025, 1, 1, tzinfo=UTC)}),
        GRANT.model_copy(update={"operation_id": "other-operation"}),
        GRANT.model_copy(update={"environment_id": "other-environment"}),
    ],
)
def test_expired_or_mismatched_grant_refuses_before_recovery(grant):
    events: list[str] = []
    result = service(events, grant=grant).run(request(raw=True))
    assert result.outcome.failure_code is EnvironmentFailureCode.RAW_GRANT_REQUIRED
    assert events == ["resolve", "instance", "policy", "grant"]


@pytest.mark.parametrize("point", [None, object()])
def test_invalid_recovery_point_refuses_before_copy(point):
    events: list[str] = []
    result = service(events, provider=Provider(events, point=point)).run(request())
    assert result.outcome.failure_code is EnvironmentFailureCode.RECOVERY_POINT_UNAVAILABLE
    assert result.lineage.policy == "policy-qa"
    assert result.lineage.recovery_point is None
    assert events == ["resolve", "instance", "policy", "acquire"]


def test_authority_and_grant_refusals_have_no_mutation():
    events: list[str] = []
    conflict = service(
        events, definition=DEFINITION.model_copy(update={"environment_id": "preprod"})
    ).run(request())
    assert conflict.outcome.failure_code is EnvironmentFailureCode.INVALID_DEFINITION
    assert events == ["resolve"]
    events.clear()
    missing = service(events, grant=None).run(request(raw=True))
    assert missing.outcome.failure_code is EnvironmentFailureCode.RAW_GRANT_REQUIRED
    assert events == ["resolve", "instance", "policy", "grant"]


def test_copy_failure_restores_and_verifies_before_terminal_failure():
    events: list[str] = []
    result = service(events, coordinator=Coordinator(events, RuntimeError())).run(request())
    assert result.outcome.failure_code is EnvironmentFailureCode.MUTATION_FAILED
    assert result.lineage.recovery_point == DEFAULT_POINT
    assert events[-3:] == ["copy", "restore", "safe-state"]


@pytest.mark.parametrize(
    "provider, code",
    [
        (
            Provider([], restore_error=RuntimeError()),
            EnvironmentFailureCode.RECOVERY_RESTORE_FAILED,
        ),
        (Provider([], verified=False), EnvironmentFailureCode.RECOVERY_VERIFICATION_FAILED),
    ],
)
def test_recovery_failures_are_explicit(provider, code):
    events: list[str] = []
    provider.events = events
    result = service(
        events, provider=provider, coordinator=Coordinator(events, RuntimeError())
    ).run(request())
    assert result.outcome.code is EnvironmentOutcomeCode.FAILED
    assert result.outcome.failure_code is code


def test_final_verification_failure_recovers():
    events: list[str] = []
    result = service(events, verify_operation=lambda result: False).run(request())
    assert result.outcome.failure_code is EnvironmentFailureCode.OPERATION_VERIFICATION_FAILED
    assert events[-3:] == ["copy", "restore", "safe-state"]
