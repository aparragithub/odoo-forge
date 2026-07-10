"""Domain error types for the local Docker backend.

These stay pure: they carry a message only and perform no I/O. Concrete
`BackendProvider` adapters (e.g. `odoo_forge_docker`) translate
subprocess/Docker-CLI failures into this typed family so the CLI can catch a
single domain error family at one boundary instead of scattering
subprocess/Docker-specific handling, mirroring `ResolutionError`/
`WorkspaceError`.
"""


class BackendError(Exception):
    """Base class for local-backend errors (`odoo_forge_docker` boundary).

    Kept as its own family so callers can catch backend-provisioning
    failures distinctly from manifest parsing/composition/resolution/
    workspace failures.
    """


class DockerUnavailableError(BackendError):
    """Raised when the `docker` binary is missing or the daemon is unreachable.

    Covers both detection paths: a missing binary (subprocess
    `FileNotFoundError`) and a present-but-unreachable daemon (non-zero exit
    with a `Cannot connect to the Docker daemon` stderr marker).
    """


class ImageNotFoundError(BackendError):
    """Raised when a required container image cannot be pulled/found."""


class ImageAuthorizationError(BackendError):
    """Raised when `docker pull` is denied by the registry or daemon."""


class PostgresReadinessError(BackendError):
    """Raised when the provisioned Postgres container never becomes TCP-ready."""


class ContainerRunError(BackendError):
    """Raised when a container fails to start or never becomes healthy."""


class InstanceNotFoundError(BackendError):
    """Raised when `status`/`stop`/`logs`/`exec` target a non-existent instance."""


class InstanceExistsError(BackendError):
    """Raised when `run` targets an instance whose containers/network already exist."""


__all__ = [
    "BackendError",
    "DockerUnavailableError",
    "ImageNotFoundError",
    "ImageAuthorizationError",
    "PostgresReadinessError",
    "ContainerRunError",
    "InstanceNotFoundError",
    "InstanceExistsError",
]
