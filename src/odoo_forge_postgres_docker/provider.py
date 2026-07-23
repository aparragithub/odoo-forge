"""Docker command and ownership-proof foundation for PostgreSQL databases."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol

from odoo_forge.credentials.errors import CredentialError as CapabilityCredentialError
from odoo_forge.credentials.types import CredentialHandle, CredentialInjectionDescriptor
from odoo_forge.data_artifacts.contracts import (
    DataArtifactCapability,
    RestoreSetComponent,
)
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import (
    CredentialUnavailableError,
    DatabaseOperationError,
    DatabaseProviderError,
    DatabaseReadinessError,
    IncompleteCleanupError,
    OwnershipRefusedError,
    ResourceUnavailableError,
)
from odoo_forge.database.readiness import RuntimeOwnershipEvidence
from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
    OperationIdentity,
    ResourceOwnership,
)
from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority
from odoo_forge_postgres_docker.secret_injection import (
    PostgreSQLSecretInjection,
    PostgreSQLSecretInjector,
)
from odoo_forge_postgres_docker.target_handoffs import (
    RestoreArtifactUnavailableError,
    materialize_database_credentials,
    validated_database_restore,
)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_PROVIDER_LABEL = "io.odoo-forge.provider"
_OPERATION_LABEL = "io.odoo-forge.operation"
_RESOURCE_KIND_LABEL = "io.odoo-forge.resource-kind"
_CREATOR_TOKEN_LABEL = "io.odoo-forge.creator-token"
_PROVIDER_NAME = "postgres-docker"
_OPERATION_PREFIX = "postgres-docker:"


class DockerCommandTimeoutError(DatabaseOperationError):
    """A bounded Docker invocation did not return in time."""


class DockerCommandFailedError(DatabaseOperationError):
    """Docker returned a nonzero status without exposing its diagnostics."""


class DockerRunner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]: ...


CredentialTarget = Callable[[CredentialInjectionDescriptor], AbstractContextManager[str]]
RestoreTarget = Callable[[RestoreSetComponent, str], bool]


def _run_subprocess(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        shell=False,
        text=True,
        timeout=timeout,
    )


def _discard_credential_descriptor(_descriptor: CredentialInjectionDescriptor) -> None:
    """Default target injector retains no credential material in the provider."""


def _unavailable_credential_target(
    _descriptor: CredentialInjectionDescriptor,
) -> AbstractContextManager[str]:
    raise CredentialUnavailableError()


def _discard_restore_component(_component: RestoreSetComponent, _target: str) -> bool:
    """Default target injector retains no artifact bytes in the provider."""
    return False


class RollbackIncompleteError(IncompleteCleanupError):
    """Redacted failure carrying the receipt required to reconcile residuals."""

    def __init__(
        self,
        receipt: CreationReceipt,
        residual_failures: tuple[str, ...],
        cleanup_failures: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.receipt = receipt
        self.residual_failures = residual_failures
        self.cleanup_failures = cleanup_failures


class DockerPostgresqlDatabaseProvider:
    """A provider boundary that refuses unproven Docker resource mutation."""

    def __init__(
        self,
        *,
        runner: DockerRunner = _run_subprocess,
        timeout: float = 10.0,
        readiness_timeout: float = 10.0,
        poll_interval: float = 0.1,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        token_factory: Callable[[], str] | None = None,
        artifact_capability: DataArtifactCapability | None = None,
        credential_materializer: Callable[[CredentialHandle], CredentialInjectionDescriptor] = (
            materialize_database_credentials
        ),
        credential_injector: Callable[[CredentialInjectionDescriptor], None] = (
            _discard_credential_descriptor
        ),
        credential_target: CredentialTarget = _unavailable_credential_target,
        restore_injector: RestoreTarget = _discard_restore_component,
        ownership_authority: LocalOwnershipAuthority | None = None,
    ) -> None:
        self._runner = runner
        self._timeout = timeout
        self._readiness_timeout = readiness_timeout
        self._poll_interval = poll_interval
        self._monotonic = monotonic
        self._sleep = sleep
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self._artifact_capability = artifact_capability
        self._credential_materializer = credential_materializer
        self._credential_injector = credential_injector
        self._credential_target = credential_target
        self._restore_injector = restore_injector
        self._ownership_authority = ownership_authority or self._default_authority()

    def inspect_resource(self, resource_id: str) -> subprocess.CompletedProcess[str]:
        """Inspect a safely named resource through an argv-only Docker call."""
        self._validate_identifier(resource_id)
        return self._run(["docker", "inspect", resource_id])

    def creation_receipt(self, resource_id: str) -> CreationReceipt:
        """Create a receipt whose operation identity carries its creator token."""
        self._validate_identifier(resource_id)
        token = self._token_factory()
        operation = OperationIdentity(value=f"{_OPERATION_PREFIX}{token}")
        return CreationReceipt(operation=operation, owned_resource_ids=(resource_id,))

    def labels_for(self, operation: OperationIdentity, *, resource_kind: str) -> dict[str, str]:
        """Return the complete live-label proof required for owned resources."""
        self._validate_identifier(resource_kind)
        return {
            _PROVIDER_LABEL: _PROVIDER_NAME,
            _OPERATION_LABEL: operation.value,
            _RESOURCE_KIND_LABEL: resource_kind,
            _CREATOR_TOKEN_LABEL: self._creator_token(operation),
        }

    def assert_live_ownership(
        self,
        receipt: CreationReceipt,
        resource_id: str,
        labels: Mapping[str, str],
        *,
        resource_kind: str,
    ) -> None:
        """Fail closed unless receipt membership and every live label agree."""
        expected = self.labels_for(receipt.operation, resource_kind=resource_kind)
        if resource_id not in receipt.owned_resource_ids or any(
            labels.get(key) != value for key, value in expected.items()
        ):
            raise OwnershipRefusedError()

    def verify_runtime_ownership(self, creation: DatabaseCreation) -> RuntimeOwnershipEvidence:
        """Attest only to a currently receipt-owned and ready Docker container."""
        if creation.ref.ownership is not ResourceOwnership.CREATED:
            raise OwnershipRefusedError()
        labels, docker_id = self._inspect_identity(creation.ref.identifier)
        self.assert_live_ownership(
            creation.receipt,
            creation.ref.identifier,
            labels,
            resource_kind="container",
        )
        if not self._owns(creation.receipt.operation.value, creation.ref.identifier, docker_id):
            raise OwnershipRefusedError()
        self._wait_ready(creation.ref.identifier)
        return object.__new__(RuntimeOwnershipEvidence)

    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        creation: DatabaseCreation | None = None
        try:
            with self._credential_target_file(credentials) as injection:
                creation = self._provision(spec, injection)
        except Exception as exc:
            rollback_incomplete = self._rollback_incomplete(exc)
            if rollback_incomplete is not None:
                if rollback_incomplete is exc:
                    raise
                raise rollback_incomplete from exc
            if creation is not None:
                # _provision fully succeeded, so the container is live, ready,
                # and owned; the only remaining failure is best-effort secret
                # cleanup on context-manager exit. Tearing the container down
                # would neither restore it nor remove any residual plaintext,
                # so the healthy resource is preserved.
                return creation
            raise
        assert creation is not None
        return creation

    def _provision(
        self, spec: DatabaseSpec, injection: PostgreSQLSecretInjection
    ) -> DatabaseCreation:
        self._validate_identifier(spec.name)
        receipt = self.creation_receipt(spec.name)
        labels = self.labels_for(receipt.operation, resource_kind="container")
        created: list[str] = []
        try:
            self._ownership_authority.reserve(receipt.operation.value, spec.name)
            argv = [
                "docker",
                "run",
                "--detach",
                "--name",
                spec.name,
            ]
            argv.extend(injection.docker_args())
            argv.extend(item for pair in labels.items() for item in ("--label", "=".join(pair)))
            argv.extend(("postgres:16",))
            try:
                self._run(argv)
                created.append(spec.name)
            except DockerCommandTimeoutError:
                live_labels, docker_id = self._inspect_identity(spec.name)
                self.assert_live_ownership(
                    receipt, spec.name, live_labels, resource_kind="container"
                )
                self._ownership_authority.bind(receipt.operation.value, spec.name, docker_id)
                self._ownership_authority.activate(receipt.operation.value, spec.name, docker_id)
                created.append(spec.name)
                raise
            live_labels, docker_id = self._inspect_identity(spec.name)
            self.assert_live_ownership(receipt, spec.name, live_labels, resource_kind="container")
            self._ownership_authority.bind(receipt.operation.value, spec.name, docker_id)
            self._ownership_authority.activate(receipt.operation.value, spec.name, docker_id)
            self._wait_ready(spec.name)
        except DatabaseProviderError as exc:
            self._raise_after_rollback(exc, receipt, created)
            raise
        except Exception as exc:
            self._raise_after_rollback(exc, receipt, created)
            raise DatabaseOperationError() from exc
        return DatabaseCreation(
            ref=DatabaseRef(identifier=spec.name, ownership=ResourceOwnership.CREATED),
            receipt=receipt,
        )

    def restore(
        self, spec: DatabaseSpec, artifact: DataArtifactRef, credentials: CredentialHandle
    ) -> DatabaseCreation:
        if self._artifact_capability is None:
            raise RestoreArtifactUnavailableError()
        component = validated_database_restore(artifact, self._artifact_capability)
        creation = self.provision(spec, credentials)
        try:
            if not self._restore_injector(component, creation.ref.identifier):
                raise DatabaseOperationError()
        except DatabaseProviderError as exc:
            self._raise_after_rollback(exc, creation.receipt, (creation.ref.identifier,))
            raise
        except Exception as exc:
            self._raise_after_rollback(exc, creation.receipt, (creation.ref.identifier,))
            raise DatabaseOperationError() from exc
        return creation

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return ref

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        self._creator_token(operation)
        listed = self._run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label={_OPERATION_LABEL}={operation.value}",
                "--format",
                "{{.Names}}",
            ]
        )
        resource_ids = tuple(identifier for identifier in listed.stdout.splitlines() if identifier)
        if not resource_ids:
            raise ResourceUnavailableError()
        receipt = CreationReceipt(operation=operation, owned_resource_ids=resource_ids)
        for resource_id in resource_ids:
            labels, docker_id = self._inspect_identity(resource_id)
            if not self._owns(operation.value, resource_id, docker_id):
                raise OwnershipRefusedError()
            self.assert_live_ownership(receipt, resource_id, labels, resource_kind="container")
        return DatabaseCreation(
            ref=DatabaseRef(identifier=resource_ids[0], ownership=ResourceOwnership.CREATED),
            receipt=receipt,
        )

    def delete(self, creation: DatabaseCreation) -> None:
        if creation.ref.ownership != "created":
            raise OwnershipRefusedError()
        self._remove_owned(creation.receipt, creation.ref.identifier)

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        for resource_id in receipt.owned_resource_ids:
            self._validate_identifier(resource_id)
        residuals = []
        for resource_id in receipt.owned_resource_ids:
            try:
                self._remove_owned(receipt, resource_id)
            except DatabaseProviderError:
                residuals.append(resource_id)
        return CleanupReport(residual_failures=tuple(residuals))

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = self._runner(argv, timeout=self._timeout)
        except FileNotFoundError as exc:
            raise DockerCommandFailedError() from exc
        except subprocess.TimeoutExpired as exc:
            raise DockerCommandTimeoutError() from exc
        if completed.returncode != 0:
            raise DockerCommandFailedError()
        return completed

    @contextmanager
    def _credential_target_file(
        self, credentials: CredentialHandle
    ) -> Iterator[PostgreSQLSecretInjection]:
        try:
            descriptor = self._credential_materializer(credentials)
            self._credential_injector(descriptor)
            with PostgreSQLSecretInjector(self._credential_target).inject(descriptor) as injection:
                yield injection
        except DatabaseProviderError:
            raise
        except CapabilityCredentialError:
            raise CredentialUnavailableError() from None
        except Exception:
            raise CredentialUnavailableError() from None

    def _inspect_labels(self, resource_id: str) -> Mapping[str, str]:
        return self._inspect_identity(resource_id)[0]

    def _inspect_identity(self, resource_id: str) -> tuple[Mapping[str, str], str]:
        inspected = self._run(["docker", "inspect", resource_id])
        try:
            inspection = json.loads(inspected.stdout)
        except (TypeError, ValueError) as exc:
            raise OwnershipRefusedError() from exc
        if (
            not isinstance(inspection, list)
            or not inspection
            or not isinstance(inspection[0], dict)
        ):
            raise OwnershipRefusedError()
        config = inspection[0].get("Config")
        docker_id = inspection[0].get("Id")
        if not isinstance(config, dict):
            raise OwnershipRefusedError()
        labels = config.get("Labels")
        if not isinstance(labels, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in labels.items()
        ):
            raise OwnershipRefusedError()
        if not isinstance(docker_id, str) or not docker_id:
            raise OwnershipRefusedError()
        return labels, docker_id

    def _wait_ready(self, resource_id: str) -> None:
        deadline = self._monotonic() + self._readiness_timeout
        while True:
            try:
                self._run(["docker", "exec", resource_id, "pg_isready", "-U", "postgres"])
                return
            except (DockerCommandFailedError, DockerCommandTimeoutError) as exc:
                if self._monotonic() >= deadline:
                    raise DatabaseReadinessError() from exc
                self._sleep(self._poll_interval)

    def _remove_owned(self, receipt: CreationReceipt, resource_id: str) -> None:
        self._validate_identifier(resource_id)
        if resource_id not in receipt.owned_resource_ids:
            raise OwnershipRefusedError()
        try:
            labels, docker_id = self._inspect_identity(resource_id)
        except DockerCommandFailedError:
            if self._resource_absent(resource_id):
                self._ownership_authority.retire_absent(receipt.operation.value, resource_id)
                return
            raise
        if not self._owns(receipt.operation.value, resource_id, docker_id):
            raise OwnershipRefusedError()
        self.assert_live_ownership(receipt, resource_id, labels, resource_kind="container")
        self._run(["docker", "rm", "-f", resource_id])
        try:
            self._ownership_authority.retire(receipt.operation.value, resource_id, docker_id)
        except DatabaseProviderError:
            if not self._resource_absent(resource_id):
                raise
            self._ownership_authority.retire_absent(
                receipt.operation.value, resource_id, docker_id=docker_id
            )

    def _resource_absent(self, resource_id: str) -> bool:
        try:
            result = self._runner(["docker", "inspect", resource_id], timeout=self._timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode != 0 and "no such object" in (result.stderr or "").lower()

    def _rollback(self, receipt: CreationReceipt, created: Sequence[str]) -> tuple[str, ...]:
        residuals = []
        for resource_id in reversed(created):
            try:
                self._remove_owned(receipt, resource_id)
            except DatabaseProviderError:
                residuals.append(resource_id)
        return tuple(residuals)

    def _owns(self, operation: str, resource_id: str, docker_id: str) -> bool:
        try:
            return self._ownership_authority.owns(operation, resource_id, docker_id)
        except DatabaseProviderError:
            return False

    def _raise_after_rollback(
        self,
        original: Exception,
        receipt: CreationReceipt,
        created: Sequence[str],
        cleanup_failures: tuple[str, ...] = (),
    ) -> None:
        residuals = self._rollback(receipt, created)
        if residuals or cleanup_failures:
            raise RollbackIncompleteError(receipt, residuals, cleanup_failures) from original

    @staticmethod
    def _rollback_incomplete(error: Exception) -> RollbackIncompleteError | None:
        seen = set()
        current: BaseException | None = error
        while current is not None and id(current) not in seen:
            if isinstance(current, RollbackIncompleteError):
                return current
            seen.add(id(current))
            current = current.__cause__ or current.__context__
        return None

    @staticmethod
    def _default_authority() -> LocalOwnershipAuthority:
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        root = state_home / "odoo-forge" / "postgres-docker"
        try:
            root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise OwnershipRefusedError() from exc
        return LocalOwnershipAuthority(root)

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if _IDENTIFIER.fullmatch(value) is None:
            raise DatabaseOperationError()

    @staticmethod
    def _creator_token(operation: OperationIdentity) -> str:
        if not operation.value.startswith(_OPERATION_PREFIX):
            raise OwnershipRefusedError()
        return operation.value.removeprefix(_OPERATION_PREFIX)


__all__ = [
    "DockerCommandFailedError",
    "DockerCommandTimeoutError",
    "DockerPostgresqlDatabaseProvider",
    "RollbackIncompleteError",
]
