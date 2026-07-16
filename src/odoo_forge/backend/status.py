"""Pure core status types + parser: `docker inspect` JSON -> `InstanceStatus`.

Mirrors `backend/plan.py`: this module performs zero I/O and never imports
`docker`/`subprocess`. `parse_status` consumes already-decoded `docker
inspect` JSON (a Python list/dict handed to it by the adapter, which owns the
actual `subprocess` call and JSON decoding); it never touches the wire.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from odoo_forge.manifest.schema import Manifest

if TYPE_CHECKING:
    from odoo_forge.backend.plan import BackendPlan, ContainerRole


_VALID_CHAR = re.compile(r"[a-z0-9_.-]")
_VALID_FIRST_CHAR = re.compile(r"[a-z0-9]")
_HASH_LEN = 8

RoleState = Literal["exited", "starting", "unhealthy", "healthy", "no_healthcheck", "unknown"]


class ExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class InstanceRef(BaseModel):
    project: str
    instance: str
    network: str
    postgres_container: str
    odoo_container: str


class RoleStatus(BaseModel):
    running: bool
    state: RoleState
    ready: bool


class InstanceStatus(BaseModel):
    odoo: RoleStatus
    postgres: RoleStatus


def sanitize_name(raw: str) -> str:
    """Map a free-form name to a deterministic Docker-safe token."""
    lowered = raw.lower()
    lossy = lowered != raw
    cleaned_chars: list[str] = []
    for char in lowered:
        if _VALID_CHAR.fullmatch(char):
            cleaned_chars.append(char)
        else:
            lossy = True
    cleaned = "".join(cleaned_chars)
    if not cleaned:
        lossy = True
    elif not _VALID_FIRST_CHAR.fullmatch(cleaned[0]):
        cleaned = f"x{cleaned}"
        lossy = True
    if not lossy:
        return cleaned
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_HASH_LEN]
    return f"{cleaned or 'x'}-{digest}"


def derive_instance_ref(manifest: Manifest, instance: str = "default") -> InstanceRef:
    """Derive a provider identity without workspace evidence or a backend plan."""
    project = sanitize_name(manifest.name)
    normalized_instance = sanitize_name(instance)
    network = f"odoo-forge-{project}-{normalized_instance}"
    return InstanceRef(
        project=project,
        instance=normalized_instance,
        network=network,
        postgres_container=f"{network}-db",
        odoo_container=f"{network}-odoo",
    )


def instance_ref(plan: BackendPlan) -> InstanceRef:
    """Build the lightweight `InstanceRef` handle from a `BackendPlan`.

    Reconstructs identity purely from the plan's own names/labels (design
    "Naming & Label Schema") — no I/O, no docker.
    """
    return InstanceRef(
        project=plan.network.labels["com.odoo-forge.project"],
        instance=plan.network.labels["com.odoo-forge.instance"],
        network=plan.network.name,
        postgres_container=plan.postgres.name,
        odoo_container=plan.odoo.name,
    )


_NOT_RUNNING = RoleStatus(running=False, state="exited", ready=False)


def _role_status(role: ContainerRole, container: dict[str, Any] | None) -> RoleStatus:
    """Derive a single role's `RoleStatus` from its `docker inspect` entry.

    Two-stage rule (design "Readiness signal: running-state first..."):
    stage 1 checks `.State.Running` BEFORE consulting health — `Running ==
    False` (or the container missing entirely) always maps to `exited`,
    never `unknown`, regardless of role or any stale health value. Stage 2
    only runs for a running container: Odoo's `.State.Health.Status` maps
    directly (`starting`/`unhealthy`/`healthy`); a null/absent health on a
    running Odoo container is unexpected and maps to `unknown` (not-ready).
    Postgres ships no HEALTHCHECK, so null/absent health on a running
    Postgres container maps to `no_healthcheck` (running, not permanently
    not-ready).
    """
    if container is None:
        return _NOT_RUNNING

    state = container.get("State") or {}
    if not state.get("Running"):
        return _NOT_RUNNING

    health = state.get("Health")
    health_status = health.get("Status") if isinstance(health, dict) else None

    if health_status == "healthy":
        return RoleStatus(running=True, state="healthy", ready=True)
    if health_status == "starting":
        return RoleStatus(running=True, state="starting", ready=False)
    if health_status == "unhealthy":
        return RoleStatus(running=True, state="unhealthy", ready=False)

    if role == "postgres":
        return RoleStatus(running=True, state="no_healthcheck", ready=False)
    return RoleStatus(running=True, state="unknown", ready=False)


def parse_status(inspect_json: list[dict[str, Any]] | dict[str, Any] | None) -> InstanceStatus:
    """Parse already-decoded `docker inspect` JSON into an `InstanceStatus`.

    Pure, zero I/O — the adapter runs `docker inspect` and decodes JSON;
    this function only interprets the result. An empty/absent/`None` result
    (container(s) externally removed) maps BOTH roles to not-running
    WITHOUT raising (design "Absent/empty inspect").
    """
    if inspect_json is None:
        containers: list[dict[str, Any]] = []
    elif isinstance(inspect_json, dict):
        containers = [inspect_json]
    else:
        containers = inspect_json

    by_role: dict[str, dict[str, Any]] = {}
    for container in containers:
        role = container.get("Config", {}).get("Labels", {}).get("com.odoo-forge.role")
        if role:
            by_role[role] = container

    return InstanceStatus(
        odoo=_role_status("odoo", by_role.get("odoo")),
        postgres=_role_status("postgres", by_role.get("postgres")),
    )


__all__ = [
    "RoleState",
    "ExecResult",
    "InstanceRef",
    "RoleStatus",
    "InstanceStatus",
    "sanitize_name",
    "derive_instance_ref",
    "instance_ref",
    "parse_status",
]
