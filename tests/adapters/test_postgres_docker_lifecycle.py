from __future__ import annotations

import fcntl
import os
import stat
import subprocess
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from odoo_forge.database.types import OperationIdentity
from odoo_forge.resource_lifecycle.types import (
    LifecycleAuthorization,
    LifecycleEvidence,
    LifecycleJournalEvent,
    LifecycleOutcome,
    LifecyclePolicy,
    ProviderPresence,
)
from odoo_forge.tenancy import ProjectScope, TenantId
from odoo_forge_postgres_docker.authority import LocalOwnershipAuthority
from odoo_forge_postgres_docker.lifecycle import (
    MAX_DOCKER_TIMEOUT,
    JsonlLifecycleJournal,
    PostgresDockerLifecycleAdapter,
    _run_docker,
)

SCOPE = ProjectScope(tenant=TenantId(value="tenant"), project_id="project")
OPERATION = OperationIdentity(value="op")
_INSPECT = (
    '[{"Id":"id","Config":{"Labels":{"io.odoo-forge.operation":"op",'
    '"io.odoo-forge.resource-class":"dev","io.odoo-forge.last-activity":"2026-01-01T00:00:00+00:00","io.odoo-forge.evidence-digest":"evidence-1"}},"State":{"Dead":false}}]'  # noqa: E501
)


def _authority(*records: object) -> SimpleNamespace:
    return SimpleNamespace(lifecycle_records=lambda: records)


def _journal_event() -> LifecycleJournalEvent:
    return LifecycleJournalEvent(
        policy=LifecyclePolicy(ttl=timedelta(days=1), grace=timedelta(days=1)),
        evidence=LifecycleEvidence(source="adapter", digest="evidence-1"),
        authorization=LifecycleAuthorization(actor="operator", reason="approved"),
        outcome=LifecycleOutcome.ALERTED,
        kind="run",
    )


def _raw_record(full: bool = True) -> dict[str, str]:
    value = {
        "operation": "op",
        "kind": "container",
        "name": "database",
        "docker_id": "id",
        "state": "active",
    }
    if full:
        value.update(
            tenant_id=SCOPE.tenant.value,
            project_id=SCOPE.project_id,
            request_digest="request-1",
            resource_class="dev",
            last_activity="2026-01-01T00:00:00+00:00",
            evidence_digest="evidence-1",
        )
    return value


def _runner(mode: str = "present") -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if mode == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        if mode == "nonzero":
            return subprocess.CompletedProcess(argv, 1, "", "failure")
        if argv[1:3] == ["ps", "-a"]:
            output = {"absent": "", "identity": "other-id\n"}.get(mode, "id\n")
            return subprocess.CompletedProcess(argv, 0, output, "")
        if mode == "malformed":
            return subprocess.CompletedProcess(argv, 0, "not-json", "")
        output = _INSPECT.replace('"Dead":false', f'"Dead":{str(mode == "dead").lower()}')
        if mode == "labels":
            output = output.replace('"op"', '"other-operation"')
        return subprocess.CompletedProcess(argv, 0, output, "")

    return run


def test_real_authority_and_legacy_rows(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_raw_record())
    result = PostgresDockerLifecycleAdapter(
        provider=Mock(), authority=authority, runner=_runner()
    ).observe(SCOPE)
    assert result[0].scope == SCOPE and result[0].presence is ProviderPresence.PRESENT
    legacy = LocalOwnershipAuthority(tmp_path / "legacy")
    legacy.write(_raw_record(False))
    assert not PostgresDockerLifecycleAdapter(provider=Mock(), authority=legacy).observe(SCOPE)


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("absent", ProviderPresence.ABSENT),
        ("dead", ProviderPresence.INVALID),
        ("present", ProviderPresence.PRESENT),
        ("malformed", ProviderPresence.UNVERIFIABLE),
        ("nonzero", ProviderPresence.UNVERIFIABLE),
        ("timeout", ProviderPresence.UNVERIFIABLE),
        ("identity", ProviderPresence.UNVERIFIABLE),
        ("labels", ProviderPresence.UNVERIFIABLE),
    ],
)
def test_provider_evidence_maps_to_typed_presence(mode: str, expected: ProviderPresence) -> None:
    record, provider = _raw_record(), Mock()
    if mode == "identity":
        record["name"] = "db;rm"
    result = PostgresDockerLifecycleAdapter(
        provider=provider, authority=_authority(record), runner=_runner(mode)
    ).observe(SCOPE)[0]
    assert result.presence is expected and provider.mock_calls == []


def test_jsonl_journal_reloads_immutable_run_and_action_records(tmp_path: Path) -> None:
    journal = JsonlLifecycleJournal(tmp_path / "lifecycle.jsonl")
    event = _journal_event()
    action = event.model_copy(update={"kind": "action", "outcome": LifecycleOutcome.QUARANTINED})
    journal.append(event)
    journal.append(action)
    assert JsonlLifecycleJournal(journal.path).events() == (event, action)


@pytest.mark.parametrize(
    "timeout", [float("inf"), float("nan"), 0.0, -1.0, MAX_DOCKER_TIMEOUT + 1.0]
)
def test_adapter_rejects_timeouts_without_a_finite_positive_bound(timeout: float) -> None:
    with pytest.raises(ValueError):
        PostgresDockerLifecycleAdapter(provider=Mock(), authority=_authority(), timeout=timeout)


def test_journal_holds_an_exclusive_lock_from_first_write_through_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real_flock, real_write, real_fsync = fcntl.flock, os.write, os.fsync

    def flock(descriptor: int, operation: int) -> None:
        order.append("lock" if operation == fcntl.LOCK_EX else "unlock")
        real_flock(descriptor, operation)

    def write(descriptor: int, data: bytes) -> int:
        order.append("write")
        return real_write(descriptor, data)

    def fsync(descriptor: int) -> None:
        order.append("fsync")
        real_fsync(descriptor)

    monkeypatch.setattr(fcntl, "flock", flock)
    monkeypatch.setattr(os, "write", write)
    monkeypatch.setattr(os, "fsync", fsync)
    JsonlLifecycleJournal(tmp_path / "lifecycle.jsonl").append(_journal_event())
    assert order.index("lock") < order.index("write") < order.index("fsync")
    assert order.index("fsync") < order.index("unlock")


def test_journal_fsyncs_parent_directory_only_when_it_creates_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directories: list[bool] = []
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        directories.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    journal = JsonlLifecycleJournal(tmp_path / "state" / "lifecycle.jsonl")
    journal.append(_journal_event())
    assert True in directories
    directories.clear()
    journal.append(_journal_event())
    assert True not in directories


def test_default_runner_uses_fixed_argv_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(subprocess, "run", run)
    _run_docker(["docker", "ps", "-a"], timeout=3.0)
    assert run.call_count == 1 and run.call_args.args == (["docker", "ps", "-a"],) and run.call_args.kwargs["shell"] is False  # noqa: E501  # fmt: skip


def test_recovery_verbs_delegate_without_provision_or_restore() -> None:
    provider = Mock()
    ref, creation, receipt = Mock(), Mock(), Mock()
    adapter = PostgresDockerLifecycleAdapter(provider=provider, authority=_authority())
    adapter.quarantine(ref)
    adapter.adopt(ref)
    adapter.reconcile(OPERATION)
    adapter.delete(creation)
    report = adapter.cleanup(receipt)
    expected = [call.quarantine(ref), call.adopt(ref), call.reconcile(OPERATION), call.delete(creation), call.cleanup(receipt)]  # noqa: E501  # fmt: skip
    assert report is provider.cleanup.return_value
    assert provider.mock_calls == expected
    assert provider.provision.call_count == provider.restore.call_count == 0
