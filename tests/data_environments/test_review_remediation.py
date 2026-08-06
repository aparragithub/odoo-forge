from unittest.mock import Mock

from odoo_forge.data_environments.service import DataEnvironmentService
from odoo_forge.data_environments.types import EnvironmentFailureCode


def test_verifier_exception_restores_and_verifies_recovery_point() -> None:
    service = object.__new__(DataEnvironmentService)
    object.__setattr__(service, "_preflight", Mock(return_value=(Mock(), None, None, None, Mock())))
    service._coordinator = Mock()
    service._verify_operation = Mock(side_effect=RuntimeError())
    service._provider = Mock()
    service._provider.verify_recovery_point.return_value = True

    result = service.run(Mock())

    assert result.outcome.failure_code is EnvironmentFailureCode.OPERATION_VERIFICATION_FAILED
    assert service._provider.restore_recovery_point.called
    assert service._provider.verify_recovery_point.called
