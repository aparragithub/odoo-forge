"""E2E `copy` command wiring (bridge slice B5): typer `CliRunner`, faked coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.credentials.types import CredentialHandle
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.database.errors import ArtifactUnavailableError, DatabaseOperationError
from odoo_forge.database.types import DatabaseCreation, DatabaseRef, DatabaseSpec, ResourceOwnership
from odoo_forge.durable_operations.types import DurableOperationIdentity, LifecycleState
from odoo_forge.resource_ownership.types import CreationReceipt, OperationIdentity
from odoo_forge_cli import _composition
from odoo_forge_cli.main import app

runner = CliRunner()


@dataclass
class _FakeCoordinatedCopyResult:
    creation: DatabaseCreation
    state: LifecycleState


class _FakeCoordinator:
    def __init__(
        self,
        result: _FakeCoordinatedCopyResult | None = None,
        error: Exception | None = None,
    ):
        self._result = result
        self._error = error
        self.run_calls: list[dict[str, object]] = []

    def run(self, **kwargs: object) -> _FakeCoordinatedCopyResult:
        self.run_calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _creation(target: str) -> DatabaseCreation:
    return DatabaseCreation(
        ref=DatabaseRef(identifier=target, ownership=ResourceOwnership.CREATED),
        receipt=CreationReceipt(
            operation=OperationIdentity(value="postgres-docker:token"),
            owned_resource_ids=(target,),
        ),
    )


def test_copy_wires_source_capture_anonymize_deliver_and_prints_the_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )

    result = runner.invoke(app, ["copy", "db-source", "db-target"])

    assert result.exit_code == 0, result.output
    assert "copied: source 'db-source' -> target 'db-target'" in result.output
    assert "no effective anonymization rules were applied" in result.output
    assert len(fake.run_calls) == 1
    call = fake.run_calls[0]
    assert isinstance(call["source"], CaptureSource)
    assert call["source"].target.kind == "source"
    assert call["source"].target.target_id == "db-source"
    assert isinstance(call["spec"], DatabaseSpec)
    assert call["spec"].name == "db-target"
    assert call["policy"] == AnonymizationPolicy()
    assert isinstance(call["credentials"], str)
    assert isinstance(call["operation"], DurableOperationIdentity)
    assert call["retain_staged"] is False


def test_copy_binds_opaque_credentials_never_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )

    runner.invoke(app, ["copy", "db-source", "db-target"])

    call = fake.run_calls[0]
    assert call["credentials"] == CredentialHandle("database-copy/db-target")
    call_source = call["source"]
    assert isinstance(call_source, CaptureSource)
    assert call_source.credentials == CredentialHandle("database-copy/db-source")


def test_copy_passes_retain_staged_flag_through(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )

    result = runner.invoke(app, ["copy", "db-source", "db-target", "--retain-staged"])

    assert result.exit_code == 0, result.output
    assert fake.run_calls[0]["retain_staged"] is True


def test_copy_configures_the_composition_root_with_the_credentials_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    seen_kwargs: dict[str, object] = {}

    def _make_coordinator(**kwargs: object) -> _FakeCoordinator:
        seen_kwargs.update(kwargs)
        return fake

    monkeypatch.setattr(_composition, "_make_data_artifact_copy_coordinator", _make_coordinator)
    credentials_file = tmp_path / "custom-credentials.sops.yaml"

    result = runner.invoke(
        app, ["copy", "db-source", "db-target", "--credentials-file", str(credentials_file)]
    )

    assert result.exit_code == 0, result.output
    assert seen_kwargs["credentials_file"] == credentials_file


def test_copy_surfaces_a_capture_failure_as_a_clean_error_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCoordinator(error=DatabaseOperationError())
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )

    result = runner.invoke(app, ["copy", "db-source", "db-target"])

    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_copy_surfaces_an_artifact_unavailable_failure_as_a_clean_error_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCoordinator(error=ArtifactUnavailableError())
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )

    result = runner.invoke(app, ["copy", "db-source", "db-target"])

    assert result.exit_code == 1
    assert "error:" in result.output


def test_copy_rejects_invalid_policy_before_constructing_coordinator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_: calls.append(True)
    )
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "version: 1\nrules:\n - table: x\n   column: y\n   mask_strategy: unknown\n"
    )

    result = runner.invoke(
        app, ["copy", "db-source", "db-target", "--anonymization-policy-file", str(policy_file)]
    )

    assert result.exit_code == 1 and not calls and "mask_strategy" in result.output


def test_copy_forwards_a_valid_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "version: 1\nrules:\n - table: x\n   column: y\n   mask_strategy: hash\n"
    )

    result = runner.invoke(
        app, ["copy", "db-source", "db-target", "--anonymization-policy-file", str(policy_file)]
    )

    assert result.exit_code == 0, result.output
    policy = fake.run_calls[0]["policy"]
    assert isinstance(policy, AnonymizationPolicy)
    assert policy.rules[0].column == "y"


def test_copy_operation_digest_tracks_policy_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )
    documents = (
        "version: 1\nrules:\n - table: x\n   column: y\n   mask_strategy: hash\n",
        "rules:\n - mask_strategy: hash\n   column: y\n   table: x\nversion: 1\n",
        "version: 1\nrules:\n - table: x\n   column: y\n   mask_strategy: redact\n",
    )

    for index, document in enumerate(documents):
        policy_file = tmp_path / f"policy-{index}.yaml"
        policy_file.write_text(document)
        result = runner.invoke(
            app, ["copy", "db-source", "db-target", "--anonymization-policy-file", str(policy_file)]
        )
        assert result.exit_code == 0, result.output

    digests = []
    for call in fake.run_calls:
        operation = call["operation"]
        assert isinstance(operation, DurableOperationIdentity)
        digests.append(operation.request_digest)
    assert digests[0] == digests[1]
    assert digests[0] != digests[2]

    for _ in range(2):
        result = runner.invoke(app, ["copy", "db-source", "db-target"])
        assert result.exit_code == 0, result.output
    assert fake.run_calls[3]["operation"] == fake.run_calls[4]["operation"]


def test_copy_identifies_an_explicit_empty_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeCoordinator(
        result=_FakeCoordinatedCopyResult(
            creation=_creation("db-target"), state=LifecycleState.SUCCEEDED
        )
    )
    monkeypatch.setattr(
        _composition, "_make_data_artifact_copy_coordinator", lambda **_kwargs: fake
    )
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("version: 1\nrules: []\n")

    result = runner.invoke(
        app, ["copy", "db-source", "db-target", "--anonymization-policy-file", str(policy_file)]
    )

    assert result.exit_code == 0, result.output
    assert "policy is empty" in result.output
