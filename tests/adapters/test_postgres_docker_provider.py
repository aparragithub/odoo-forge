"""Safety contracts for the isolated Docker PostgreSQL adapter."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from inspect import getsource
from typing import get_type_hints

import pytest

import odoo_forge_postgres_docker.provider as provider_module
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.data_artifacts.types import DataArtifactRef
from odoo_forge.database.errors import DatabaseOperationError, OwnershipRefusedError
from odoo_forge.database.types import DatabaseCreation, DatabaseSpec
from odoo_forge.ports.database_provider import DatabaseProvider
from odoo_forge_postgres_docker.provider import (
    DockerCommandFailedError,
    DockerCommandTimeoutError,
    DockerPostgresqlDatabaseProvider,
)


def test_hostile_resource_name_is_rejected_before_subprocess_execution() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    provider = DockerPostgresqlDatabaseProvider(runner=runner)

    with pytest.raises(DatabaseOperationError) as excinfo:
        provider.inspect_resource("db; touch /tmp/pwned")

    assert str(excinfo.value) == "database provider operation failed"
    assert calls == []


def test_safe_resource_name_is_passed_as_a_single_argv_argument() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    result = DockerPostgresqlDatabaseProvider(runner=runner).inspect_resource("safe-db")

    assert result.stdout == "[]"
    assert calls == [("docker", "inspect", "safe-db")]


@pytest.mark.parametrize(
    ("runner", "error_type"),
    [
        (
            lambda _argv, *, timeout: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(["docker"], timeout)
            ),
            DockerCommandTimeoutError,
        ),
        (
            lambda argv, *, timeout: subprocess.CompletedProcess(
                argv, 1, "", "fatal: password=super-secret"
            ),
            DockerCommandFailedError,
        ),
    ],
)
def test_docker_failures_are_typed_and_redacted(
    runner: object, error_type: type[DatabaseOperationError]
) -> None:
    provider = DockerPostgresqlDatabaseProvider(runner=runner)  # type: ignore[arg-type]

    with pytest.raises(error_type) as excinfo:
        provider.inspect_resource("safe-db")

    assert str(excinfo.value) == "database provider operation failed"
    assert "super-secret" not in str(excinfo.value)


def test_mismatched_live_labels_refuse_mutation() -> None:
    provider = DockerPostgresqlDatabaseProvider()
    receipt = provider.creation_receipt("safe-db")
    labels = provider.labels_for(receipt.operation, resource_kind="container")
    labels["io.odoo-forge.creator-token"] = "forged-token"

    with pytest.raises(OwnershipRefusedError) as excinfo:
        provider.assert_live_ownership(receipt, "safe-db", labels, resource_kind="container")

    assert str(excinfo.value) == "database resource ownership does not permit this operation"


def test_matching_live_labels_and_receipt_membership_prove_ownership() -> None:
    provider = DockerPostgresqlDatabaseProvider()
    receipt = provider.creation_receipt("safe-db")

    provider.assert_live_ownership(
        receipt,
        "safe-db",
        provider.labels_for(receipt.operation, resource_kind="container"),
        resource_kind="container",
    )


def test_adapter_conforms_to_database_provider_protocol_without_docker_import() -> None:
    provider = DockerPostgresqlDatabaseProvider()

    assert isinstance(provider, DatabaseProvider)
    assert "odoo_forge_docker" not in provider.__class__.__module__


def test_adapter_preserves_database_provider_type_contracts() -> None:
    provision_hints = get_type_hints(DockerPostgresqlDatabaseProvider.provision)
    restore_hints = get_type_hints(DockerPostgresqlDatabaseProvider.restore)

    assert provision_hints == {
        "spec": DatabaseSpec,
        "credentials": CredentialHandle,
        "return": DatabaseCreation,
    }
    assert restore_hints["artifact"] is DataArtifactRef
    assert restore_hints["credentials"] is CredentialHandle


def test_adapter_source_stays_isolated_from_local_backend_routing() -> None:
    source = getsource(provider_module)

    assert "odoo_forge_docker" not in source
    assert "DockerBackendProvider" not in source
    assert "odoo_forge_cli" not in source
