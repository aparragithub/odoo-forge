"""Operation-bound VPS backend and HTTP exposure adapter."""

# The provider is intentionally kept as one bounded review slice; long command
# tuples remain readable as fixed argv and are excluded from line-length lint.
# fmt: off
# ruff: noqa: E501, I001

from __future__ import annotations

import hashlib
import json
import socket
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.request import urlopen

from odoo_forge.backend.destruction import DestroyResourceResult, DestroyResult
from odoo_forge.backend.plan import BackendPlan, ContainerRole
from odoo_forge.backend.status import ExecResult, InstanceRef, InstanceStatus, instance_ref, parse_status
from odoo_forge.credentials.types import CredentialHandle, CredentialResolver
from odoo_forge.deployment_spec.types import DeploymentSpec
from odoo_forge.durable_operations.service import build_terminal_commit, save_checkpoint
from odoo_forge.durable_operations.types import DurableOperationIdentity, LifecycleState, RedactedEvidence
from odoo_forge.exposure.types import ExposureCheckStatus, ExposureOutcome, ExposureRequest, ExposureResult
from odoo_forge.ports.durable_operation_store import DurableOperationRecord, DurableOperationStore
from odoo_forge.resource_ownership.types import OwnershipReceipt, OwnershipRecord, ResourceOwnership, ResourceRef
from odoo_forge.tenancy.types import ProjectScope
from odoo_forge_docker.vps.transport import MutationState, OpenSshTarget, OpenSshTransport


_OPERATION_LABEL = "com.odoo-forge.operation"
_CREATOR_TOKEN_LABEL = "com.odoo-forge.creator-token"
_DELETE_COMMANDS = {
    "container": ("docker", "rm", "-f"),
    "network": ("docker", "network", "rm"),
    "volume": ("docker", "volume", "rm"),
}
_MANAGED_ODOO_IMAGE_PREFIXES = (
    "odoo-forge-odoo:",
    "ghcr.io/aparragithub/odoo-ce:",
    "ghcr.io/aparragithub/odoo-ce@",
)
_ODOO_READINESS_TIMEOUT_SECONDS = 90.0


@dataclass(frozen=True)
class VpsTargetIdentity:
    host: str
    user: str
    port: int
    host_key: str


@dataclass(frozen=True)
class VpsOperationBinding:
    scope: ProjectScope
    operation: DurableOperationIdentity
    verb: str
    ownership: tuple[OwnershipRecord, ...]
    target: VpsTargetIdentity
    credential_handles: tuple[CredentialHandle, ...]


class VpsMechanics(Protocol):
    def ensure_runtime(self, plan: BackendPlan, operation: DurableOperationIdentity) -> tuple[OwnershipRecord, ...]: ...
    def discover_runtime(self, ref: InstanceRef) -> tuple[OwnershipRecord, ...]: ...
    def runtime_ready(self, ref: InstanceRef) -> bool: ...
    def runtime_status(self, ref: InstanceRef) -> InstanceStatus: ...
    def ensure_http(self, ref: InstanceRef, hostname: str, operation: DurableOperationIdentity) -> OwnershipRecord: ...
    def verify_http(self, hostname: str) -> bool: ...
    def verify_dns(self, hostname: str, target: str) -> bool: ...
    def stop(self, ref: InstanceRef) -> None: ...
    def destroy(self, ref: InstanceRef, ownership: tuple[OwnershipRecord, ...]) -> None: ...
    def destroy_result(self, ref: InstanceRef) -> DestroyResult: ...
    def logs(self, ref: InstanceRef, role: ContainerRole) -> str: ...
    def exec(self, ref: InstanceRef, argv: tuple[str, ...]) -> ExecResult: ...


def _creator_token(operation: DurableOperationIdentity, kind: str, identifier: str) -> str:
    return hashlib.sha256(f"{operation.operation_id}:{kind}:{identifier}".encode()).hexdigest()


def _owned(
    operation: DurableOperationIdentity,
    kind: str,
    identifier: str,
    *,
    live_id: str | None = None,
) -> OwnershipRecord:
    return OwnershipRecord(
        ref=ResourceRef(identifier=identifier, resource_kind=kind, ownership=ResourceOwnership.CREATED),
        receipt=OwnershipReceipt(
            operation=operation,
            owned_resource_ids=(live_id or identifier,),
        ),
    )


class RemoteDockerMechanics:
    """Remote Docker commands are routed exclusively through Unit 2 SSH."""

    def __init__(self, target: VpsTargetIdentity, private_key: str, *, timeout: float = 30.0, credential_resolver: CredentialResolver | None = None) -> None:
        self._ssh = OpenSshTransport(OpenSshTarget(target.host, target.user, target.port, target.host_key, private_key), timeout=timeout)
        self._credential_resolver = credential_resolver
        self._scope: ProjectScope | None = None
        self._pointer: str | None = None
        self._secret_paths: set[str] = set()

    def _run(self, command: Sequence[str], *, mutating: bool = False) -> str:
        return self._ssh.run(command, mutating=mutating).stdout

    def bind_scope(self, scope: ProjectScope, instance: str) -> None:
        self._scope, self._pointer = scope, f"{scope.tenant.value}/{scope.project_id}/{instance}"

    def _exists(self, kind: str, identifier: str) -> bool:
        command = {
            "network": ("docker", "network", "ls", "-q", "--filter", f"name=^{identifier}$"),
            "volume": ("docker", "volume", "ls", "-q", "--filter", f"name=^{identifier}$"),
            "container": ("docker", "container", "ls", "-aq", "--filter", f"name=^{identifier}$"),
        }[kind]
        return bool(self._run(command).strip())

    def _inspect(self, identifier: str, kind: str) -> dict[str, Any] | None:
        if not self._exists(kind, identifier):
            return None
        output = self._run(("docker", "inspect", identifier))
        if not output.strip():
            return None
        decoded = json.loads(output)
        if not isinstance(decoded, list) or not decoded or not isinstance(decoded[0], dict):
            raise ValueError("remote inspect returned invalid resource data")
        return cast(dict[str, Any], decoded[0])

    @staticmethod
    def _labels(entry: dict[str, Any]) -> dict[str, str]:
        labels = entry.get("Config", {}).get("Labels") if "Config" in entry else entry.get("Labels")
        return cast(dict[str, str], labels or {})

    def _expected_labels(self, plan_labels: dict[str, str]) -> dict[str, str]:
        expected: dict[str, str] = dict(plan_labels)
        scope = getattr(self, "_scope", None)
        if scope is not None:
            expected.update({
                "com.odoo-forge.managed": "true",
                "com.odoo-forge.tenant": scope.tenant.value,
                "com.odoo-forge.project": scope.project_id,
                "com.odoo-forge.pointer": getattr(self, "_pointer", "") or "",
            })
        return expected

    def _validate_live(self, identifier: str, entry: dict[str, Any] | None, expected: dict[str, str]) -> None:
        if entry is None:
            return
        labels = self._labels(entry)
        if any(labels.get(key) != value for key, value in expected.items()):
            raise ValueError(f"live resource scope mismatch for {identifier}")

    def validate_scope(self, plan: BackendPlan, scope: ProjectScope) -> None:
        if plan.network.labels.get("com.odoo-forge.project") != scope.project_id:
            raise ValueError("plan project is outside the bound scope")
        self.bind_scope(scope, plan.network.labels.get("com.odoo-forge.instance", "default"))
        resources = (
            ("network", plan.network.name, plan.network.labels),
            *(('volume', volume.name, volume.labels) for volume in plan.volumes),
            ("container", plan.postgres.name, plan.postgres.labels),
            ("container", plan.odoo.name, plan.odoo.labels),
        )
        for kind, identifier, labels in resources:
            self._validate_live(identifier, self._inspect(identifier, kind), self._expected_labels(labels))

    def validate_exposure(self, ref: InstanceRef, scope: ProjectScope, pointer: str) -> None:
        if ref.project != scope.project_id or pointer != self._pointer:
            raise ValueError("deployment pointer is outside the bound scope")
        self.bind_scope(scope, ref.instance)
        expected = self._expected_labels({"com.odoo-forge.project": ref.project, "com.odoo-forge.instance": ref.instance})
        self._validate_live(ref.network, self._inspect(ref.network, "network"), expected)
        self._validate_live(ref.postgres_container, self._inspect(ref.postgres_container, "container"), {**expected, "com.odoo-forge.role": "postgres"})
        self._validate_live(ref.odoo_container, self._inspect(ref.odoo_container, "container"), {**expected, "com.odoo-forge.role": "odoo"})

    def _preflight(self, plan: BackendPlan) -> dict[str, dict[str, Any] | None]:
        resources = (
            ("network", plan.network.name, plan.network.labels),
            *(('volume', volume.name, volume.labels) for volume in plan.volumes),
            ("container", plan.postgres.name, plan.postgres.labels),
            ("container", plan.odoo.name, plan.odoo.labels),
        )
        inspected = {identifier: self._inspect(identifier, kind) for kind, identifier, _ in resources}
        for _kind, identifier, labels in resources:
            self._validate_live(identifier, inspected[identifier], self._expected_labels(labels))
        return inspected

    def _resource_record(self, operation: DurableOperationIdentity, kind: str, identifier: str, created: bool) -> OwnershipRecord:
        if created:
            return _owned(operation, kind, identifier)
        return OwnershipRecord(ref=ResourceRef(identifier=identifier, resource_kind=kind, ownership=ResourceOwnership.ADOPTED))

    def _create_volume(self, volume: Any, operation: DurableOperationIdentity) -> OwnershipRecord:
        labels = {
            **self._expected_labels(volume.labels),
            **volume.labels,
            _OPERATION_LABEL: operation.operation_id,
            _CREATOR_TOKEN_LABEL: _creator_token(operation, "volume", volume.name),
        }
        args = ["docker", "volume", "create"]
        for key, value in labels.items():
            args.extend(("--label", f"{key}={value}"))
        output = self._run((*args, volume.name), mutating=True)
        return _owned(operation, "volume", volume.name, live_id=output.strip() or volume.name)

    def _container_command(self, spec: Any, operation: DurableOperationIdentity, postgres_credentials: CredentialHandle | None = None, container_command: tuple[str, ...] = ()) -> OwnershipRecord:
        command = ["docker", "run", "-d", "--name", spec.name, "--network", spec.network]
        labels = {
            **self._expected_labels(spec.labels),
            **spec.labels,
            _OPERATION_LABEL: operation.operation_id,
            _CREATOR_TOKEN_LABEL: _creator_token(operation, "container", spec.name),
        }
        for key, value in labels.items():
            command.extend(("--label", f"{key}={value}"))
        for key, value in spec.env.items():
            command.extend(("--env", f"{key}={value}"))
        secret_paths: list[str] = []
        resolver = getattr(self, "_credential_resolver", None)
        try:
            secrets = dict(spec.secret_env)
            if spec.role == "postgres" and postgres_credentials is not None and resolver is not None:
                secrets["POSTGRES_PASSWORD"] = postgres_credentials
            if resolver is None and secrets:
                raise ValueError("opaque credential resolver is required")
            if spec.role == "odoo" and secrets:
                assert resolver is not None
                path = f"/tmp/odoo-forge-secret-{hashlib.sha256(spec.name.encode()).hexdigest()[:16]}"
                env_file = "".join(f"{key}={resolver(handle)}\n" for key, handle in secrets.items())
                self._ssh.upload_secret(env_file, path)
                secret_paths.append(path)
                if not hasattr(self, "_secret_paths"):
                    self._secret_paths = set()
                self._secret_paths.add(path)
                command.extend(("--env-file", path))
            elif secrets:
                assert resolver is not None
                for key, handle in secrets.items():
                    path = f"/tmp/odoo-forge-secret-{hashlib.sha256(str(handle).encode()).hexdigest()[:16]}"
                    self._ssh.upload_secret(resolver(handle), path)
                    secret_paths.append(path)
                    if not hasattr(self, "_secret_paths"):
                        self._secret_paths = set()
                    self._secret_paths.add(path)
                    command.extend(("--volume", f"{path}:/run/secrets/{key}:ro", "--env", f"{key}_FILE=/run/secrets/{key}"))
            target = "/var/lib/postgresql/data" if spec.role == "postgres" else "/var/lib/odoo"
            for volume in spec.volumes:
                command.extend(("--volume", f"{volume.name}:{target}"))
            for mount in spec.mounts:
                mode = "ro" if mount.read_only else "rw"
                command.extend(("--volume", f"{mount.host_path}:{mount.container_path}:{mode}"))
            for container_port, host_port in spec.ports.items():
                command.extend(("--publish", f"{spec.bind_host}:{host_port or 0}:{container_port}"))
            output = self._run((*command, spec.image, *container_command), mutating=True)
        except Exception:
            for path in secret_paths:
                with suppress(Exception):
                    self._ssh.run(("rm", "-f", path), mutating=True)
                self._secret_paths.discard(path)
            raise
        return _owned(operation, "container", spec.name, live_id=output.strip() or spec.name)

    def _cleanup_secret_paths(self) -> None:
        for path in tuple(getattr(self, "_secret_paths", ())):
            with suppress(Exception):
                self._ssh.run(("rm", "-f", path), mutating=True)
            self._secret_paths.discard(path)

    def ensure_runtime(self, plan: BackendPlan, operation: DurableOperationIdentity) -> tuple[OwnershipRecord, ...]:
        inspected = self._preflight(plan)
        records: list[OwnershipRecord] = []
        try:
            if inspected[plan.network.name] is None:
                labels = {
                    **self._expected_labels(plan.network.labels),
                    **plan.network.labels,
                    _OPERATION_LABEL: operation.operation_id,
                    _CREATOR_TOKEN_LABEL: _creator_token(operation, "network", plan.network.name),
                }
                args = ["docker", "network", "create"]
                for key, value in labels.items():
                    args.extend(("--label", f"{key}={value}"))
                output = self._run((*args, plan.network.name), mutating=True)
                records.append(_owned(operation, "network", plan.network.name, live_id=output.strip() or plan.network.name))
            else:
                records.append(self._resource_record(operation, "network", plan.network.name, False))
            for volume in plan.volumes:
                created = inspected[volume.name] is None
                records.append(self._create_volume(volume, operation) if created else self._resource_record(operation, "volume", volume.name, False))
            for spec in (plan.postgres, plan.odoo):
                created = inspected[spec.name] is None
                if created and spec.role == "odoo" and spec.image.startswith(_MANAGED_ODOO_IMAGE_PREFIXES):
                    pgdata_created = any(
                        item.ref.resource_kind == "volume"
                        and item.ref.identifier == plan.postgres.volumes[0].name
                        and item.ref.ownership is ResourceOwnership.CREATED
                        for item in records
                    ) if plan.postgres.volumes else False
                    if pgdata_created:
                        database = spec.env.get("POSTGRES_DB")
                        if database is None:
                            raise ValueError("managed Odoo bootstrap requires POSTGRES_DB")
                        bootstrap = spec.model_copy(update={"name": f"{spec.name}-bootstrap", "ports": {}})
                        bootstrap_record = self._container_command(
                            bootstrap,
                            operation,
                            plan.postgres_credentials,
                            container_command=("odoo", "-d", database, "-i", "base", "--stop-after-init", "--no-http"),
                        )
                        records.append(bootstrap_record)
                        if self._run(("docker", "wait", bootstrap.name), mutating=True).strip() != "0":
                            raise RuntimeError("managed Odoo database bootstrap failed")
                        self._run(("docker", "rm", "-f", bootstrap.name), mutating=True)
                        records.remove(bootstrap_record)
                records.append(self._container_command(spec, operation, plan.postgres_credentials) if created else self._resource_record(operation, "container", spec.name, False))
            return tuple(records)
        except Exception as exc:
            if getattr(exc, "state", None) not in (MutationState.UNKNOWN_POST_MUTATION, "unknown_post_mutation"):
                self._destroy_owned(tuple(item for item in records if item.ref.ownership is ResourceOwnership.CREATED))
                self._cleanup_secret_paths()
            raise

    def discover_runtime(self, ref: InstanceRef) -> tuple[OwnershipRecord, ...]:
        names = (("network", ref.network), ("container", ref.postgres_container), ("container", ref.odoo_container))
        expected = self._expected_labels({"com.odoo-forge.project": ref.project, "com.odoo-forge.instance": ref.instance})
        records: list[OwnershipRecord] = []
        for kind, name in names:
            entry = self._inspect(name, kind)
            self._validate_live(name, entry, expected)
            if entry is not None:
                records.append(self._resource_record(DurableOperationIdentity(operation_id="adopted", request_digest=""), kind, name, False))
        return tuple(records)

    def runtime_ready(self, ref: InstanceRef) -> bool:
        try:
            deadline = time.monotonic() + _ODOO_READINESS_TIMEOUT_SECONDS
            while True:
                entries = json.loads(self._run(("docker", "inspect", ref.postgres_container, ref.odoo_container)))
                statuses = [entry.get("State", {}).get("Health", {}).get("Status") for entry in entries]
                if not all(bool(entry.get("State", {}).get("Running")) for entry in entries) or "unhealthy" in statuses:
                    return False
                if "starting" in statuses:
                    if time.monotonic() >= deadline:
                        return False
                    time.sleep(1.0)
                    continue
                odoo_entry = next((entry for entry in entries if entry.get("Name", "").lstrip("/") == ref.odoo_container), None)
                image = odoo_entry.get("Config", {}).get("Image", "") if odoo_entry else ""
                if not isinstance(image, str) or not image.startswith(_MANAGED_ODOO_IMAGE_PREFIXES):
                    return True
                try:
                    return bool(self._run(("docker", "exec", ref.odoo_container, "curl", "--fail", "--silent", "--show-error", "--max-time", "5", "http://127.0.0.1:8069/web/health")).strip())
                except Exception:
                    return False
        finally:
            self._cleanup_secret_paths()

    def runtime_status(self, ref: InstanceRef) -> InstanceStatus:
        return parse_status(json.loads(self._run(("docker", "inspect", ref.postgres_container, ref.odoo_container))))

    def ensure_http(self, ref: InstanceRef, hostname: str, operation: DurableOperationIdentity) -> OwnershipRecord:
        return _owned(operation, "http", f"{ref.network}-http")

    def verify_http(self, hostname: str) -> bool:
        try:
            with urlopen(f"http://{hostname}/", timeout=5.0) as response:
                return cast(int, response.status) == 200
        except OSError:
            return False

    def verify_dns(self, hostname: str, target: str) -> bool:
        return target in {item[4][0] for item in socket.getaddrinfo(hostname, 80)}

    def stop(self, ref: InstanceRef) -> None:
        for name in (ref.odoo_container, ref.postgres_container):
            self._run(("docker", "stop", name), mutating=True)

    def _proves_created(self, record: OwnershipRecord) -> tuple[str, dict[str, str]] | None:
        if record.ref.ownership is not ResourceOwnership.CREATED or record.receipt is None:
            return None
        if len(record.receipt.owned_resource_ids) != 1:
            return None
        try:
            entry = self._inspect(record.ref.identifier, record.ref.resource_kind)
            if entry is None:
                return None
            identity = self._live_identity(entry, record.ref.resource_kind, record.ref.identifier)
            labels = self._labels(entry)
            expected_token = _creator_token(record.receipt.operation, record.ref.resource_kind, record.ref.identifier)
            if identity != record.receipt.owned_resource_ids[0] or labels.get(_OPERATION_LABEL) != record.receipt.operation.operation_id or labels.get(_CREATOR_TOKEN_LABEL) != expected_token:
                return None
            return identity, labels
        except Exception:
            return None

    @staticmethod
    def _live_identity(entry: dict[str, Any], kind: str, identifier: str) -> str:
        value = entry.get("Name") if kind == "volume" else entry.get("Id")
        if not isinstance(value, str) or not value:
            raise ValueError("live resource identity is missing")
        return value

    def _destroy_owned(self, ownership: tuple[OwnershipRecord, ...]) -> None:
        for record in reversed(ownership):
            command = _DELETE_COMMANDS.get(record.ref.resource_kind)
            proof = self._proves_created(record) if command is not None else None
            if command is None or proof is None:
                continue
            self._run((*command, proof[0]), mutating=True)

    def destroy(self, ref: InstanceRef, ownership: tuple[OwnershipRecord, ...]) -> None:
        self._destroy_owned(ownership)

    def destroy_result(self, ref: InstanceRef) -> DestroyResult:
        return DestroyResult(resources=tuple(DestroyResourceResult(kind="container", identifier=name, outcome="removed") for name in (ref.odoo_container, ref.postgres_container)))

    def logs(self, ref: InstanceRef, role: ContainerRole) -> str:
        return self._run(("docker", "logs", ref.odoo_container if role == "odoo" else ref.postgres_container))

    def exec(self, ref: InstanceRef, argv: tuple[str, ...]) -> ExecResult:
        return ExecResult(exit_code=0, stdout=self._run(("docker", "exec", ref.odoo_container, *argv)), stderr="")


def request_digest(verb: str, scope: ProjectScope, target: VpsTargetIdentity, handles: tuple[CredentialHandle, ...], payload: object, ownership: tuple[OwnershipRecord, ...] = ()) -> str:
    value: Any = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    if isinstance(payload, ExposureRequest):
        value["operation"] = {"operation_id": payload.operation.operation_id}
    owners = tuple((item.ref.identifier, item.ref.resource_kind, item.ref.ownership.value, item.receipt.owned_resource_ids if item.receipt else ()) for item in ownership)
    raw = json.dumps({"verb": verb, "scope": scope.model_dump(mode="json"), "target": target.__dict__, "handles": tuple(handles), "ownership": owners, "payload": value}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _ownership_evidence(ownership: tuple[OwnershipRecord, ...]) -> tuple[RedactedEvidence, ...]:
    """Retain only safe receipt references in durable evidence.

    The provider-neutral durable operation contract stores redacted evidence, not
    provider records. Receipt identifiers are therefore carried as opaque,
    validated references while ownership state remains an adapter concern.
    """
    evidence: list[RedactedEvidence] = []
    for record in ownership:
        receipt = record.receipt
        if receipt is None or not receipt.owned_resource_ids:
            continue
        evidence.append(
            RedactedEvidence(
                event="ownership_verified",
                summary="verified ownership receipt retained",
                references=receipt.owned_resource_ids,
            )
        )
    return tuple(evidence)

class VpsBackendProvider:
    def __init__(self, binding: VpsOperationBinding, store: DurableOperationStore, mechanics: VpsMechanics) -> None:
        self._binding, self._store, self._mechanics = binding, store, mechanics
        if any(item.attribution and item.attribution.tenant_id != binding.scope.tenant.value for item in binding.ownership):
            raise ValueError("ownership is outside the bound tenant")

    def request_digest(self, payload: object) -> str:
        return request_digest(self._binding.verb, self._binding.scope, self._binding.target, self._binding.credential_handles, payload, self._binding.ownership)

    def _begin(self, method: str, payload: object, *, ref: InstanceRef | None = None, handles: tuple[CredentialHandle, ...] = ()) -> DurableOperationRecord:
        if self._binding.verb != method or (ref is not None and ref.project != self._binding.scope.project_id) or (handles and handles != self._binding.credential_handles):
            raise ValueError("operation binding mismatch")
        if not self._binding.operation.matches_request_digest(self.request_digest(payload)):
            raise ValueError("operation request meaning mismatch")
        return self._store.create_or_load(self._binding.operation)

    def _checkpoint(self, record: DurableOperationRecord, phase: str, summary: str, refs: tuple[str, ...] = ()) -> DurableOperationRecord:
        evidence = RedactedEvidence(event=phase, summary=summary, references=refs)
        return self._store.save_checkpoint(record.identity.operation_id, record.revision, save_checkpoint(record.revision, phase, evidence))

    def _terminal(
        self,
        record: DurableOperationRecord,
        outcome: LifecycleState,
        evidence: tuple[RedactedEvidence, ...],
        ownership: tuple[OwnershipRecord, ...] = (),
    ) -> None:
        durable_evidence = evidence + _ownership_evidence(ownership)
        self._store.commit_terminal(
            record.identity.operation_id,
            build_terminal_commit(record.revision, outcome, durable_evidence, ()),
        )

    def _prepare_runtime(self, plan: BackendPlan, ref: InstanceRef) -> None:
        binder = getattr(self._mechanics, "bind_scope", None)
        if binder is not None:
            binder(self._binding.scope, ref.instance)
        validator = getattr(self._mechanics, "validate_scope", None)
        if validator is not None:
            validator(plan, self._binding.scope)

    def run(self, plan: BackendPlan) -> InstanceRef:
        handles = (*plan.odoo.secret_env.values(), *([plan.postgres_credentials] if plan.postgres_credentials else ()))
        record, ref, owned = self._begin("run", plan, handles=handles), instance_ref(plan), cast(Any, ())
        if record.lifecycle in (LifecycleState.SUCCEEDED, LifecycleState.CLOSED):
            return ref
        try:
            self._prepare_runtime(plan, ref)
            owned = self._mechanics.ensure_runtime(plan, record.identity)
            record = self._checkpoint(record, "runtime", "managed runtime reconciled", tuple(item.ref.identifier for item in owned))
            if not self._mechanics.runtime_ready(ref):
                raise RuntimeError("managed runtime is not ready")
            record = self._checkpoint(record, "ready", "managed runtime readiness verified")
            self._terminal(record, LifecycleState.SUCCEEDED, record.recovery_evidence, owned)
            return ref
        except Exception as exc:
            if getattr(exc, "state", None) in (MutationState.UNKNOWN_POST_MUTATION, "unknown_post_mutation"):
                self._store.mark_reconciliation_required(record.identity.operation_id, record.revision)
            else:
                created = tuple(item for item in owned if item.ref.ownership is ResourceOwnership.CREATED)
                if created:
                    self._mechanics.destroy(ref, created)
                self._terminal(
                    record,
                    LifecycleState.FAILED,
                    record.recovery_evidence
                    or (RedactedEvidence(event="failed", summary="runtime operation failed"),),
                    owned,
                )
            raise

    def status(self, ref: InstanceRef) -> InstanceStatus:
        record = self._begin("status", ref, ref=ref)
        if record.lifecycle not in (LifecycleState.SUCCEEDED, LifecycleState.CLOSED):
            self._checkpoint(record, "observed", "runtime status observed")
        return self._mechanics.runtime_status(ref)

    def stop(self, ref: InstanceRef) -> None:
        record = self._begin("stop", ref, ref=ref)
        if record.lifecycle not in (LifecycleState.SUCCEEDED, LifecycleState.CLOSED):
            try:
                self._mechanics.stop(ref)
            except Exception as exc:
                if getattr(exc, "state", None) in (MutationState.UNKNOWN_POST_MUTATION, "unknown_post_mutation"):
                    self._store.mark_reconciliation_required(record.identity.operation_id, record.revision)
                raise
            self._terminal(record, LifecycleState.SUCCEEDED, (RedactedEvidence(event="stopped", summary="runtime stopped"),))

    def destroy(self, ref: InstanceRef) -> DestroyResult:
        record = self._begin("destroy", ref, ref=ref)
        if record.lifecycle not in (LifecycleState.SUCCEEDED, LifecycleState.CLOSED):
            try:
                self._mechanics.destroy(ref, tuple(item for item in self._binding.ownership if item.ref.ownership is ResourceOwnership.CREATED))
            except Exception as exc:
                if getattr(exc, "state", None) in (MutationState.UNKNOWN_POST_MUTATION, "unknown_post_mutation"):
                    self._store.mark_reconciliation_required(record.identity.operation_id, record.revision)
                raise
            self._terminal(record, LifecycleState.SUCCEEDED, (RedactedEvidence(event="destroyed", summary="owned runtime destroyed"),))
        return self._mechanics.destroy_result(ref)

    def logs(self, ref: InstanceRef, role: ContainerRole) -> str:
        if role not in ("odoo", "postgres"):
            raise ValueError("invalid container role")
        self._begin("logs", (ref, role), ref=ref)
        return self._mechanics.logs(ref, role)

    def exec(self, ref: InstanceRef, argv: Sequence[str]) -> ExecResult:
        self._begin("exec", (ref, tuple(argv)), ref=ref)
        return self._mechanics.exec(ref, tuple(argv))

    def reconcile(self, request: ExposureRequest) -> ExposureResult:
        record = self._begin("reconcile", request, ref=request.instance)
        exposure: DeploymentSpec = request.deployment
        if exposure.exposure is None:
            raise ValueError("HTTP exposure intent is required")
        pointer = exposure.pointer
        if request.scope != self._binding.scope or pointer.scope != self._binding.scope or pointer.instance_id.value != request.instance.instance or exposure.resource.identifier != request.instance.network:
            raise ValueError("deployment pointer is outside the bound scope")
        binder = getattr(self._mechanics, "bind_scope", None)
        if binder is not None:
            binder(self._binding.scope, request.instance.instance)
        validator = getattr(self._mechanics, "validate_exposure", None)
        if validator is not None:
            validator(request.instance, self._binding.scope, f"{pointer.scope.tenant.value}/{pointer.scope.project_id}/{pointer.instance_id.value}")
        route: OwnershipRecord | None = None
        try:
            host = exposure.exposure.hostname
            route = self._mechanics.ensure_http(request.instance, host, record.identity)
            http = self._mechanics.verify_http(host)
            dns = self._mechanics.verify_dns(host, self._binding.target.host)
            result = ExposureResult(operation=record.identity, outcome=ExposureOutcome.READY if http and dns else ExposureOutcome.IN_PROGRESS, routing_status=ExposureCheckStatus.VERIFIED if http else ExposureCheckStatus.PENDING, dns_status=ExposureCheckStatus.VERIFIED if dns else ExposureCheckStatus.PENDING, ready=http and dns, ownership=(route,), evidence=(RedactedEvidence(event="exposure", summary="HTTP exposure reconciled"),))
            if http and dns:
                self._terminal(record, LifecycleState.SUCCEEDED, result.evidence, (route,))
            return result
        except Exception as exc:
            if getattr(exc, "state", None) in (MutationState.UNKNOWN_POST_MUTATION, "unknown_post_mutation"):
                self._store.mark_reconciliation_required(record.identity.operation_id, record.revision)
            elif route is not None and route.ref.ownership is ResourceOwnership.CREATED:
                self._mechanics.destroy(request.instance, (route,))
            if getattr(exc, "state", None) not in (MutationState.UNKNOWN_POST_MUTATION, "unknown_post_mutation"):
                self._terminal(
                    record,
                    LifecycleState.FAILED,
                    (RedactedEvidence(event="exposure_failed", summary="exposure reconciliation failed"),),
                    (route,) if route is not None else (),
                )
            raise


def bind_vps_operation(binding: VpsOperationBinding, *, store: DurableOperationStore, mechanics: VpsMechanics | None = None, credentials: CredentialResolver | None = None) -> VpsBackendProvider:
    if mechanics is None:
        if credentials is None or not binding.credential_handles:
            raise ValueError("VPS binding requires opaque credential resolution")
        mechanics = RemoteDockerMechanics(binding.target, credentials(binding.credential_handles[0]), credential_resolver=credentials)
    return VpsBackendProvider(binding, store, mechanics)


__all__ = ["RemoteDockerMechanics", "VpsBackendProvider", "VpsMechanics", "VpsOperationBinding", "VpsTargetIdentity", "bind_vps_operation", "request_digest"]
