from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict

from odoo_forge.database.types import (
    CleanupReport,
    CreationReceipt,
    DatabaseCreation,
    DatabaseRef,
    OperationIdentity,
    ResourceOwnership,
)
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.resource_lifecycle.types import (
    DatabaseObservation,
    LifecycleJournalEvent,
    ProviderPresence,
    ResourceClass,
)
from odoo_forge.resource_ownership.types import OwnershipReceipt
from odoo_forge.tenancy.types import ProjectScope, TenantId

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DOCKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_OPERATION_LABEL = "io.odoo-forge.operation"
_CLASS_LABEL = "io.odoo-forge.resource-class"
_ACTIVITY_LABEL = "io.odoo-forge.last-activity"
_DIGEST_LABEL = "io.odoo-forge.evidence-digest"


class LifecycleAuthorityRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    resource: DatabaseRef
    scope: ProjectScope
    operation: DurableOperationIdentity
    docker_id: str
    resource_class: ResourceClass
    last_activity: AwareDatetime
    evidence_digest: str


def _run_docker(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv), capture_output=True, check=False, shell=False, text=True, timeout=timeout
    )


class PostgresDockerLifecycleAdapter:
    def __init__(
        self,
        *,
        provider: Any,
        authority: Any,
        runner: Callable[..., subprocess.CompletedProcess[str]] = _run_docker,
        timeout: float = 10.0,
    ) -> None:
        self.provider = provider
        self.authority = authority
        self._runner = runner
        self._timeout = timeout

    def observe(self, scope: ProjectScope) -> tuple[DatabaseObservation, ...]:
        records = tuple(
            record
            for raw in self.authority.lifecycle_records()
            if (record := _coerce_record(raw)) is not None
        )
        counts: dict[str, int] = {}
        for record in records:
            counts[record.resource.identifier] = counts.get(record.resource.identifier, 0) + 1
        observations: list[DatabaseObservation] = []
        for record in records:
            if record.scope != scope:
                continue
            if counts[record.resource.identifier] != 1:
                observations.append(self._observation(record, ProviderPresence.UNVERIFIABLE))
                continue
            observations.append(self._observe_record(record))
        return tuple(observations)

    def _observe_record(self, record: LifecycleAuthorityRecord) -> DatabaseObservation:
        try:
            if _IDENTIFIER.fullmatch(record.resource.identifier) is None:
                raise ValueError("unsafe resource identifier")
            if _DOCKER_ID.fullmatch(record.docker_id) is None:
                raise ValueError("unsafe Docker identity")
            listed = self._run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--no-trunc",
                    "--filter",
                    f"id={record.docker_id}",
                    "--format",
                    "{{.ID}}",
                ]
            )
            lines = tuple(line for line in listed.stdout.splitlines() if line)
            if not lines:
                return self._observation(record, ProviderPresence.ABSENT)
            if lines != (record.docker_id,):
                raise ValueError("docker identity did not match authority")
            inspected = self._run(["docker", "inspect", record.docker_id])
            payload = json.loads(inspected.stdout)
            if (
                not isinstance(payload, list)
                or len(payload) != 1
                or not isinstance(payload[0], dict)
            ):
                raise ValueError("malformed inspect result")
            entry = payload[0]
            if entry.get("Id") != record.docker_id:
                raise ValueError("docker identity did not match inspect")
            config = entry.get("Config")
            state = entry.get("State")
            labels = config.get("Labels") if isinstance(config, dict) else None
            if not isinstance(labels, dict) or not isinstance(state, dict):
                raise ValueError("missing live evidence")
            if any(
                labels.get(key) != value
                for key, value in {
                    _OPERATION_LABEL: record.operation.operation_id,
                    _CLASS_LABEL: record.resource_class.value,
                    _ACTIVITY_LABEL: record.last_activity.isoformat(),
                    _DIGEST_LABEL: record.evidence_digest,
                }.items()
            ):
                raise ValueError("live evidence contradicted authority")
            dead = state.get("Dead")
            if not isinstance(dead, bool):
                raise ValueError("missing dead state")
            return self._observation(
                record, ProviderPresence.INVALID if dead else ProviderPresence.PRESENT
            )
        except Exception:
            return self._observation(record, ProviderPresence.UNVERIFIABLE)

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        result = self._runner(argv, timeout=self._timeout)
        if result.returncode != 0 or not isinstance(result.stdout, str):
            raise ValueError("docker command failed")
        return result

    @staticmethod
    def _observation(
        record: LifecycleAuthorityRecord, presence: ProviderPresence
    ) -> DatabaseObservation:
        receipt = OwnershipReceipt(
            operation=record.operation,
            owned_resource_ids=(record.resource.identifier,),
        )
        return DatabaseObservation(
            ref=record.resource,
            scope=record.scope,
            evidence_digest=record.evidence_digest,
            ownership_valid=record.resource.ownership is not ResourceOwnership.EXTERNAL,
            resource_class=record.resource_class,
            last_activity=record.last_activity,
            receipt=receipt,
            presence=presence,
        )

    def quarantine(self, ref: DatabaseRef) -> DatabaseRef:
        return cast(DatabaseRef, self.provider.quarantine(ref))

    def adopt(self, ref: DatabaseRef) -> DatabaseRef:
        return cast(DatabaseRef, self.provider.adopt(ref))

    def reconcile(self, operation: OperationIdentity) -> DatabaseCreation:
        return cast(DatabaseCreation, self.provider.reconcile(operation))

    def delete(self, creation: DatabaseCreation) -> None:
        self.provider.delete(creation)

    def cleanup(self, receipt: CreationReceipt) -> CleanupReport:
        return cast(CleanupReport, self.provider.cleanup(receipt))


class JsonlLifecycleJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: LifecycleJournalEvent) -> LifecycleJournalEvent:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        try:
            encoded = (event.model_dump_json() + "\n").encode()
            while encoded:
                written = os.write(descriptor, encoded)
                if written <= 0:
                    raise OSError("journal write made no progress")
                encoded = encoded[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return event

    def events(self) -> tuple[LifecycleJournalEvent, ...]:
        if not self.path.exists():
            return ()
        return tuple(
            LifecycleJournalEvent.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line
        )


def _coerce_record(raw: object) -> LifecycleAuthorityRecord | None:
    if isinstance(raw, LifecycleAuthorityRecord):
        return raw
    if not isinstance(raw, Mapping) or raw.get("state") != "active":
        return None
    try:
        values = cast(Mapping[str, Any], raw)
        return LifecycleAuthorityRecord(
            resource=DatabaseRef(identifier=values["name"], ownership=ResourceOwnership.CREATED),
            scope=ProjectScope(
                tenant=TenantId(value=values["tenant_id"]), project_id=values["project_id"]
            ),
            operation=DurableOperationIdentity(
                operation_id=values["operation"], request_digest=values["request_digest"]
            ),
            docker_id=values["docker_id"],
            resource_class=ResourceClass(values["resource_class"]),
            last_activity=values["last_activity"],
            evidence_digest=values["evidence_digest"],
        )
    except (KeyError, TypeError, ValueError):
        return None
