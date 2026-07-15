"""Docker command and ownership-proof foundation for PostgreSQL databases."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import (
    DatabaseOperationError,
    DatabaseProviderError,
    DatabaseReadinessError,
    OwnershipRefusedError,
    ResourceUnavailableError,
)
from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
    OperationIdentity,
    ResourceOwnership,
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


def _run_subprocess(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        shell=False,
        text=True,
        timeout=timeout,
    )


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
    ) -> None:
        self._runner = runner
        self._timeout = timeout
        self._readiness_timeout = readiness_timeout
        self._poll_interval = poll_interval
        self._monotonic = monotonic
        self._sleep = sleep
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))

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

    def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation:
        self._validate_identifier(spec.name)
        receipt = self.creation_receipt(spec.name)
        labels = self.labels_for(receipt.operation, resource_kind="container")
        created = [spec.name]
        try:
            argv = ["docker", "run", "--detach", "--name", spec.name]
            argv.extend(item for pair in labels.items() for item in ("--label", "=".join(pair)))
            argv.extend(("postgres:16",))
            self._run(argv)
            self.assert_live_ownership(
                receipt, spec.name, self._inspect_labels(spec.name), resource_kind="container"
            )
            self._wait_ready(spec.name)
        except Exception:
            self._rollback(receipt, created)
            raise
        return DatabaseCreation(
            ref=DatabaseRef(identifier=spec.name, ownership=ResourceOwnership.CREATED),
            receipt=receipt,
        )

    def restore(
        self, spec: DatabaseSpec, artifact: DataArtifactRef, credentials: CredentialHandle
    ) -> DatabaseCreation:
        raise NotImplementedError("restore is implemented in the handoff slice")

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
                "{{.ID}}",
            ]
        )
        resource_ids = tuple(identifier for identifier in listed.stdout.splitlines() if identifier)
        if not resource_ids:
            raise ResourceUnavailableError()
        receipt = CreationReceipt(operation=operation, owned_resource_ids=resource_ids)
        for resource_id in resource_ids:
            self.assert_live_ownership(
                receipt, resource_id, self._inspect_labels(resource_id), resource_kind="container"
            )
        return DatabaseCreation(
            ref=DatabaseRef(identifier=resource_ids[0], ownership=ResourceOwnership.CREATED),
            receipt=receipt,
        )

    def delete(self, creation: DatabaseCreation) -> None:
        if creation.ref.ownership != "created":
            raise OwnershipRefusedError()
        self._remove_owned(creation.receipt, creation.ref.identifier)

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
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
        except subprocess.TimeoutExpired as exc:
            raise DockerCommandTimeoutError() from exc
        if completed.returncode != 0:
            raise DockerCommandFailedError()
        return completed

    def _inspect_labels(self, resource_id: str) -> Mapping[str, str]:
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
        if not isinstance(config, dict):
            raise OwnershipRefusedError()
        labels = config.get("Labels")
        if not isinstance(labels, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in labels.items()
        ):
            raise OwnershipRefusedError()
        return labels

    def _wait_ready(self, resource_id: str) -> None:
        deadline = self._monotonic() + self._readiness_timeout
        while True:
            completed = self._runner(
                ["docker", "exec", resource_id, "pg_isready", "-U", "postgres"],
                timeout=self._timeout,
            )
            if completed.returncode == 0:
                return
            if self._monotonic() >= deadline:
                raise DatabaseReadinessError()
            self._sleep(self._poll_interval)

    def _remove_owned(self, receipt: CreationReceipt, resource_id: str) -> None:
        if resource_id not in receipt.owned_resource_ids:
            raise OwnershipRefusedError()
        self.assert_live_ownership(
            receipt,
            resource_id,
            self._inspect_labels(resource_id),
            resource_kind="container",
        )
        self._run(["docker", "rm", "-f", resource_id])

    def _rollback(self, receipt: CreationReceipt, created: Sequence[str]) -> None:
        for resource_id in reversed(created):
            try:
                self._remove_owned(receipt, resource_id)
            except DatabaseProviderError:
                continue

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
]
