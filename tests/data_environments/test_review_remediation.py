from unittest.mock import Mock

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.data_environments.service import (
    DataEnvironmentOperationRequest,
    DataEnvironmentService,
)
from odoo_forge.data_environments.types import EnvironmentFailureCode, EnvironmentLifecycle
from odoo_forge.database.types import RecoveryPoint


def test_verifier_exception_restores_and_verifies_recovery_point() -> None:
    scope, provider, coordinator, instances = (Mock() for _ in range(4))
    definition = Mock(
        environment_id="target",
        lifecycle=EnvironmentLifecycle.ACTIVE,
        scope=scope,
        relationships=(Mock(source_environment_id="source", target_environment_id="target"),),
    )
    instances.get.return_value = Mock(receipt=object(), resource=Mock(identifier="database"))
    provider.acquire_recovery_point.return_value = RecoveryPoint("point")
    service = DataEnvironmentService(
        environment_registry=Mock(resolve=Mock(return_value=definition)),
        instance_registry=instances,
        raw_grant_authority=Mock(),
        database_provider=provider,
        coordinator=coordinator,
        policy_resolver=lambda ref: AnonymizationPolicy(),
        verify_operation=Mock(side_effect=RuntimeError()),
    )
    request = DataEnvironmentOperationRequest(
        operation=Mock(),
        source_environment_id="source",
        target_environment_id="target",
        target_pointer=Mock(scope=scope),
        target_ref=Mock(identifier="database"),
        source=Mock(target=Mock(target_id="source")),
        spec=Mock(),
        credentials=Mock(),
        actor="actor",
        intent="intent",
    )
    result = service.run(request)
    assert result.outcome.failure_code is EnvironmentFailureCode.OPERATION_VERIFICATION_FAILED
    assert provider.restore_recovery_point.called and provider.verify_recovery_point.called
