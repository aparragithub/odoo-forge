"""Docker command and ownership-proof foundation for PostgreSQL databases."""

from __future__ import annotations

import re
import secrets
import subprocess
from collections.abc import Mapping, Sequence
from typing import Protocol

from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import DatabaseOperationError, OwnershipRefusedError
from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    DatabaseSpec,
    OperationIdentity,
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

    def __init__(self, *, runner: DockerRunner = _run_subprocess, timeout: float = 10.0) -> None:
        self._runner = runner
        self._timeout = timeout

    def inspect_resource(self, resource_id: str) -> subprocess.CompletedProcess[str]:
        """Inspect a safely named resource through an argv-only Docker call."""
        self._validate_identifier(resource_id)
        return self._run(["docker", "inspect", resource_id])

    def creation_receipt(self, resource_id: str) -> CreationReceipt:
        """Create a receipt whose operation identity carries its creator token."""
        self._validate_identifier(resource_id)
        token = secrets.token_urlsafe(24)
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
        raise NotImplementedError("provisioning is implemented in the lifecycle slice")

    def restore(
        self, spec: DatabaseSpec, artifact: DataArtifactRef, credentials: CredentialHandle
    ) -> DatabaseCreation:
        raise NotImplementedError("restore is implemented in the handoff slice")

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        raise NotImplementedError("adoption is implemented in the lifecycle slice")

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        raise NotImplementedError("reconciliation is implemented in the lifecycle slice")

    def delete(self, creation: DatabaseCreation) -> None:
        raise NotImplementedError("deletion is implemented in the lifecycle slice")

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        raise NotImplementedError("cleanup is implemented in the lifecycle slice")

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = self._runner(argv, timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            raise DockerCommandTimeoutError() from exc
        if completed.returncode != 0:
            raise DockerCommandFailedError()
        return completed

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
