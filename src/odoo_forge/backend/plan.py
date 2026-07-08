"""Pure core planner: `Manifest` + `MaterializedState` -> `BackendPlan`.

Mirrors `manifest/projection.py`: this module performs zero I/O and never
imports `docker`/`subprocess`. It turns declarative intent into typed specs
(`NetworkSpec`/`VolumeSpec`/`ContainerSpec`/`BackendPlan`); the adapter
(`odoo_forge_docker`, a later PR of this slice) maps those specs to `docker`
CLI argv.
"""

import hashlib
import re
from typing import Literal

from pydantic import BaseModel

from odoo_forge.manifest.projection import MOUNT_ROOTS
from odoo_forge.manifest.schema import Manifest
from odoo_forge.manifest.state import MaterializedState

ContainerRole = Literal["odoo", "postgres"]

# Deterministic local-dev credentials — this is a LOCAL backend; the values
# match the entrypoint's own fallbacks (`entrypoint.sh:143-159`) so behavior
# is identical whether or not they are set explicitly. A generated password
# is a documented future option, not this slice (design "Env & credentials").
_DB_USER = "odoo"
_DB_PASSWORD = "odoo"
_POSTGRES_PORT = "5432"

_ODOO_IMAGE_TEMPLATE = "odoo-forge-odoo:{odoo_version}"
_POSTGRES_IMAGE = "postgres:16"

_VALID_CHAR = re.compile(r"[a-z0-9_.-]")
_VALID_FIRST_CHAR = re.compile(r"[a-z0-9]")
_HASH_LEN = 8


def sanitize_name(raw: str) -> str:
    """Map a free-form `str` (e.g. `manifest.name`) to a docker-safe token.

    Pure, unary, always-on lossy-hash rule (design "sanitize_name: degenerate
    manifest names"): a name that is ALREADY a valid docker token
    (`[a-z0-9][a-z0-9_.-]*`, no character lost) is returned UNCHANGED. Any
    LOSSY transform — a changed/dropped character, an empty result, or an
    invalid first character — appends a short deterministic hash of the RAW
    input, so two distinct raw names that collapse to the same sanitized stem
    still land on distinct, deterministic outputs.
    """
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
        cleaned = ""
    elif not _VALID_FIRST_CHAR.fullmatch(cleaned[0]):
        cleaned = f"x{cleaned}"
        lossy = True

    if not lossy:
        return cleaned

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_HASH_LEN]
    base = cleaned or "x"
    return f"{base}-{digest}"


class Mount(BaseModel):
    root: str
    host_path: str
    container_path: str
    read_only: bool


class NetworkSpec(BaseModel):
    name: str
    labels: dict[str, str]


class VolumeSpec(BaseModel):
    name: str
    labels: dict[str, str]


class ContainerSpec(BaseModel):
    name: str
    image: str
    role: ContainerRole
    network: str
    env: dict[str, str]
    mounts: list[Mount] = []
    labels: dict[str, str]
    volumes: list[VolumeSpec] = []
    ports: dict[str, int | None] = {}


class BackendPlan(BaseModel):
    network: NetworkSpec
    volumes: list[VolumeSpec]
    postgres: ContainerSpec
    odoo: ContainerSpec


def _labels(project: str, instance: str, role: str | None = None) -> dict[str, str]:
    labels = {
        "com.odoo-forge.project": project,
        "com.odoo-forge.instance": instance,
        "com.odoo-forge.managed": "true",
    }
    if role is not None:
        labels["com.odoo-forge.role"] = role
    return labels


def plan_backend(
    manifest: Manifest, state: MaterializedState, instance: str = "default"
) -> BackendPlan:
    """Compute a `BackendPlan` from `manifest`/`state`. Pure, zero I/O.

    `state` is accepted for interface symmetry with the design's data flow
    (`Manifest + MaterializedState -> plan_backend()`) and to keep this
    signature stable for later slices (e.g. seeding); this PR's mount plan
    is the fixed 5-root table (`entrypoint.sh:82` scans all five and skips
    absent directories at runtime, so mounting unconditionally is safe).
    """
    del state  # unused this PR — see docstring; kept for signature stability

    project = sanitize_name(manifest.name)
    db_name = project

    network_name = f"odoo-forge-{project}-{instance}"
    postgres_name = f"odoo-forge-{project}-{instance}-db"
    odoo_name = f"odoo-forge-{project}-{instance}-odoo"

    pgdata_volume = VolumeSpec(
        name=f"{network_name}-pgdata",
        labels=_labels(project, instance, role="postgres"),
    )
    filestore_volume = VolumeSpec(
        name=f"{network_name}-filestore",
        labels=_labels(project, instance, role="odoo"),
    )

    mounts = [
        Mount(
            root=root,
            host_path=str(path),
            container_path=str(path),
            read_only=root != "worktrees",
        )
        for root, path in MOUNT_ROOTS.items()
    ]

    postgres_spec = ContainerSpec(
        name=postgres_name,
        image=_POSTGRES_IMAGE,
        role="postgres",
        network=network_name,
        env={
            "POSTGRES_PASSWORD": _DB_PASSWORD,
            "POSTGRES_USER": _DB_USER,
            "POSTGRES_DB": db_name,
        },
        mounts=[],
        labels=_labels(project, instance, role="postgres"),
        volumes=[pgdata_volume],
        ports={},
    )

    odoo_spec = ContainerSpec(
        name=odoo_name,
        image=_ODOO_IMAGE_TEMPLATE.format(odoo_version=manifest.odoo_version),
        role="odoo",
        network=network_name,
        env={
            "DB_HOST": postgres_name,
            "DB_PORT": _POSTGRES_PORT,
            "DB_USER": _DB_USER,
            "DB_PASSWORD": _DB_PASSWORD,
            "POSTGRES_DB": db_name,
        },
        mounts=mounts,
        labels=_labels(project, instance, role="odoo"),
        volumes=[filestore_volume],
        ports={"8069": None, "8072": None},
    )

    return BackendPlan(
        network=NetworkSpec(name=network_name, labels=_labels(project, instance)),
        volumes=[pgdata_volume, filestore_volume],
        postgres=postgres_spec,
        odoo=odoo_spec,
    )


__all__ = [
    "ContainerRole",
    "Mount",
    "NetworkSpec",
    "VolumeSpec",
    "ContainerSpec",
    "BackendPlan",
    "plan_backend",
    "sanitize_name",
]
