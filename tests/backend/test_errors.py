from odoo_forge.backend.errors import (
    BackendError,
    ContainerRunError,
    DockerUnavailableError,
    ImageAuthorizationError,
    ImageNotFoundError,
    InstanceExistsError,
    InstanceNotFoundError,
    PostgresReadinessError,
)


def test_backend_error_family() -> None:
    assert issubclass(DockerUnavailableError, BackendError)
    assert issubclass(ImageNotFoundError, BackendError)
    assert issubclass(ImageAuthorizationError, BackendError)
    assert issubclass(PostgresReadinessError, BackendError)
    assert issubclass(ContainerRunError, BackendError)
    assert issubclass(InstanceNotFoundError, BackendError)
    assert issubclass(InstanceExistsError, BackendError)
    assert issubclass(BackendError, Exception)
