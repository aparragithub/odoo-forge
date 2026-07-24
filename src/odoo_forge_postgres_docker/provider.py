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
        if spec.network is not None:
            self._validate_identifier(spec.network)
        if spec.data_volume is not None:
            self._validate_identifier(spec.data_volume)
        self._reject_reserved_label_collisions(spec.labels)
        receipt = self.creation_receipt(spec.name)
        data_volume_ownership = ResourceOwnership.CREATED
        created_volume: str | None = None
        if spec.data_volume is not None:
            data_volume_ownership = self._ensure_data_volume(spec.data_volume, receipt.operation)
            if data_volume_ownership is ResourceOwnership.CREATED:
                created_volume = spec.data_volume
                receipt = CreationReceipt(
                    operation=receipt.operation,
                    owned_resource_ids=(*receipt.owned_resource_ids, spec.data_volume),
                )
        labels = self.labels_for(receipt.operation, resource_kind="container")
        # `spec.labels` collisions with the reserved `io.odoo-forge.*`
        # namespace are already rejected above, so this merge can never
        # override the ownership proof labels.
        merged_labels = {**labels, **spec.labels}
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
            if spec.network is not None:
                argv.extend(("--network", spec.network))
            if spec.data_volume is not None:
                argv.extend(("-v", f"{spec.data_volume}:/var/lib/postgresql/data"))
            argv.extend(injection.docker_args())
            # `spec.env`/`spec.labels` flow directly into `docker run` argv and
            # are visible via `docker inspect`; they MUST NOT carry secret
            # material (documented non-goal). Postgres credentials are
            # delivered exclusively through `PostgreSQLSecretInjection`
            # (bind-mounted `POSTGRES_PASSWORD_FILE`), never via env/labels.
            for key, value in spec.env.items():
                argv.extend(("-e", f"{key}={value}"))
            argv.extend(
                item for pair in merged_labels.items() for item in ("--label", "=".join(pair))
            )
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
            self._wait_ready(spec.name, spec.env)
        except DatabaseProviderError as exc:
            self._raise_after_rollback(exc, receipt, created, created_volume=created_volume)
            raise
        except Exception as exc:
            self._raise_after_rollback(exc, receipt, created, created_volume=created_volume)
            raise DatabaseOperationError() from exc
        return DatabaseCreation(
            # The container is always freshly `docker run` by this call, so
            # `ref.ownership` MUST always report CREATED — it is load-bearing
            # for the container lifecycle (`delete()`/`verify_runtime_ownership()`
            # gate on it). Data-volume freshness rides the dedicated
            # `data_volume_ownership` field instead (R2-001 fix).
            ref=DatabaseRef(identifier=spec.name, ownership=ResourceOwnership.CREATED),
            receipt=receipt,
            data_volume_ownership=data_volume_ownership,
        )

    def _reject_reserved_label_collisions(self, labels: Mapping[str, str]) -> None:
        """Fail closed when caller labels collide with the reserved namespace.

        Caller-supplied `spec.labels` MUST NOT be able to spoof or erase the
        `io.odoo-forge.*` ownership/proof labels. Checked before any docker
        call and before `merged_labels` is built.
        """
        if any(key.startswith("io.odoo-forge.") for key in labels):
            raise DatabaseOperationError()

    def _ensure_data_volume(
        self, volume_name: str, operation: OperationIdentity
    ) -> ResourceOwnership:
        """Inspect a named data volume; create and label it only when absent.

        A pre-existing volume is never owned (never labelled, never added to
        the receipt) so it is never removed by cleanup or rollback. This is
        the fresh-pgdata signal: only a genuinely fresh volume reports
        ``CREATED``.
        """
        try:
            self._run(["docker", "volume", "inspect", volume_name])
            return ResourceOwnership.ADOPTED
        except DockerCommandFailedError:
            pass
        labels = self.labels_for(operation, resource_kind="volume")
        argv = ["docker", "volume", "create"]
        argv.extend(item for pair in labels.items() for item in ("--label", "=".join(pair)))
        argv.append(volume_name)
        self._run(argv)
        return ResourceOwnership.CREATED

    def restore(
        self, spec: DatabaseSpec, artifact: DataArtifactRef, credentials: CredentialHandle
    ) -> DatabaseCreation:
        if self._artifact_capability is None:
            raise RestoreArtifactUnavailableError()
        component = validated_database_restore(artifact, self._artifact_capability)
        creation = self.provision(spec, credentials)
        # Thread the freshly-created data volume (if any) through this
        # call's own rollback, symmetrically with `_provision`, so a failed
        # restore never leaks a provider-created volume that a subsequent
        # run would misclassify as ADOPTED (WARNING fix).
        created_volume = (
            spec.data_volume
            if spec.data_volume is not None
            and creation.data_volume_ownership is ResourceOwnership.CREATED
            else None
        )
        try:
            if not self._restore_injector(component, creation.ref.identifier):
                raise DatabaseOperationError()
        except DatabaseProviderError as exc:
            self._raise_after_rollback(
                exc, creation.receipt, (creation.ref.identifier,), created_volume=created_volume
            )
            raise
        except Exception as exc:
            self._raise_after_rollback(
                exc, creation.receipt, (creation.ref.identifier,), created_volume=created_volume
            )
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

    def _wait_ready(self, resource_id: str, env: Mapping[str, str] | None = None) -> None:
        user = (env or {}).get("POSTGRES_USER", "postgres")
        argv = ["docker", "exec", resource_id, "pg_isready", "-U", user]
        database = (env or {}).get("POSTGRES_DB")
        if database is not None:
            argv.extend(("-d", database))
        deadline = self._monotonic() + self._readiness_timeout
        while True:
            try:
                self._run(argv)
                return
            except (DockerCommandFailedError, DockerCommandTimeoutError) as exc:
                if self._monotonic() >= deadline:
                    raise DatabaseReadinessError() from exc
                self._sleep(self._poll_interval)

    def _remove_owned(self, receipt: CreationReceipt, resource_id: str) -> None:
        """Remove an owned resource, dispatching by its `resource-kind` label.

        Container-kind resources are removed via `docker rm -f` with a
        `resource_kind="container"` ownership assertion (unchanged
        behavior). Volume-kind resources are removed via `docker volume rm`
        with a `resource_kind="volume"` ownership assertion instead — a
        receipt legitimately owning both kinds (fresh data volume + always-
        created container) must not have its volume entries mistakenly torn
        down via the container subcommand (R4-001 fix).
        """
        self._validate_identifier(resource_id)
        if resource_id not in receipt.owned_resource_ids:
            raise OwnershipRefusedError()
        try:
            kind, labels, identity = self._inspect_owned_resource(resource_id)
        except DockerCommandFailedError:
            if self._resource_absent(resource_id):
                self._ownership_authority.retire_absent(receipt.operation.value, resource_id)
                return
            raise
        if kind == "volume":
            self._remove_owned_volume(receipt, resource_id, labels)
            return
        self._remove_owned_container(receipt, resource_id, labels, identity)

    def _remove_owned_volume(
        self, receipt: CreationReceipt, resource_id: str, labels: Mapping[str, str]
    ) -> None:
        self.assert_live_ownership(receipt, resource_id, labels, resource_kind="volume")
        self._run(["docker", "volume", "rm", resource_id])

    def _remove_owned_container(
        self, receipt: CreationReceipt, resource_id: str, labels: Mapping[str, str], docker_id: str
    ) -> None:
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

    def _inspect_owned_resource(self, resource_id: str) -> tuple[str, Mapping[str, str], str]:
        """Return `(resource_kind, labels, identity)` via generic docker inspect.

        A container's JSON entry nests labels under `Config.Labels` and
        carries an immutable `Id`; a volume's entry carries `Labels`
        directly and uses its `Name` as identity (volumes have no separate
        immutable id). This single generic `docker inspect` call is reused
        unchanged for containers, so no existing call pattern regresses.
        """
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
        entry = inspection[0]
        config = entry.get("Config")
        if isinstance(config, dict):
            kind = "container"
            labels = config.get("Labels")
            identity = entry.get("Id")
        else:
            kind = "volume"
            labels = entry.get("Labels")
            identity = entry.get("Name")
        if not isinstance(labels, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in labels.items()
        ):
            raise OwnershipRefusedError()
        if not isinstance(identity, str) or not identity:
            raise OwnershipRefusedError()
        return kind, labels, identity

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
        created_volume: str | None = None,
    ) -> None:
        residuals = self._rollback(receipt, created)
        if created_volume is not None:
            residuals = (*residuals, *self._rollback_data_volume(created_volume))
        if residuals or cleanup_failures:
            raise RollbackIncompleteError(receipt, residuals, cleanup_failures) from original

    def _rollback_data_volume(self, volume_name: str) -> tuple[str, ...]:
        """Remove a freshly-created data volume this same call provisioned.

        Only ever invoked for a volume this `_provision` call itself created
        (``created_volume``); a pre-existing (adopted) volume is never passed
        here, so it is never removed on rollback.
        """
        try:
            self._run(["docker", "volume", "rm", "-f", volume_name])
        except DatabaseProviderError:
            return (volume_name,)
        return ()

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
