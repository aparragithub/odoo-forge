"""Pure core planner: `Manifest` + `MountPlanningView` -> `BackendPlan`.

Mirrors `manifest/projection.py`: this module performs zero I/O and never
imports `docker`/`subprocess`. It turns declarative intent into typed specs
(`NetworkSpec`/`VolumeSpec`/`ContainerSpec`/`BackendPlan`); the adapter
(`odoo_forge_docker`, a later PR of this slice) maps those specs to `docker`
CLI argv.
"""

from typing import Literal

from pydantic import BaseModel

from odoo_forge.backend.status import derive_instance_ref, sanitize_name
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.manifest.projection import MountPlanningView
from odoo_forge.manifest.schema import Manifest

ContainerRole = Literal["odoo", "postgres"]

_DB_USER = "odoo"
_POSTGRES_PORT = "5432"

_ODOO_IMAGE_TEMPLATE = "odoo-forge-odoo:{odoo_version}"
_POSTGRES_IMAGE = "postgres:16"


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
    secret_env: dict[str, CredentialHandle] = {}
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
    manifest: Manifest,
    mount_view: MountPlanningView,
    instance: str = "default",
    odoo_image: str | None = None,
    credentials: BackendCredentialBindings | None = None,
) -> BackendPlan:
    """Compute a `BackendPlan` from validated evidence. Pure, zero I/O."""
    mounts = [
        Mount(
            root=evidence.container_path.parts[2],
            host_path=str(evidence.source_path),
            container_path=str(evidence.container_path),
            read_only=evidence.read_only,
        )
        for evidence in mount_view.mounts
    ]
    ref = derive_instance_ref(manifest, instance)
    project = ref.project
    instance = ref.instance
    db_name = project
    network_name = ref.network

    pgdata_volume = VolumeSpec(
        name=f"{network_name}-pgdata",
        labels=_labels(project, instance, role="postgres"),
    )
    filestore_volume = VolumeSpec(
        name=f"{network_name}-filestore",
        labels=_labels(project, instance, role="odoo"),
    )

    postgres_spec = ContainerSpec(
        name=ref.postgres_container,
        image=_POSTGRES_IMAGE,
        role="postgres",
        network=network_name,
        env={
            "POSTGRES_USER": _DB_USER,
            "POSTGRES_DB": db_name,
        },
        secret_env=(
            {"POSTGRES_PASSWORD": credentials.postgres_password} if credentials is not None else {}
        ),
        mounts=[],
        labels=_labels(project, instance, role="postgres"),
        volumes=[pgdata_volume],
        ports={},
    )

    odoo_spec = ContainerSpec(
        name=ref.odoo_container,
        image=(
            odoo_image
            if odoo_image is not None
            else _ODOO_IMAGE_TEMPLATE.format(odoo_version=manifest.odoo_version)
        ),
        role="odoo",
        network=network_name,
        env={
            "DB_HOST": ref.postgres_container,
            "DB_PORT": _POSTGRES_PORT,
            "DB_USER": _DB_USER,
            "POSTGRES_DB": db_name,
        },
        secret_env={"DB_PASSWORD": credentials.odoo_db_password} if credentials is not None else {},
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
