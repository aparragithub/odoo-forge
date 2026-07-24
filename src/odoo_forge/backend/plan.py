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
from odoo_forge.manifest.projection import MountPlanningView, ordered_addons_roots
from odoo_forge.manifest.schema import DEFAULT_ODOO_BIND_HOST, Manifest

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
    bind_host: str = DEFAULT_ODOO_BIND_HOST
    ports: dict[str, int | None] = {}


class BackendPlan(BaseModel):
    network: NetworkSpec
    volumes: list[VolumeSpec]
    postgres: ContainerSpec
    odoo: ContainerSpec
    # Dedicated carrier for the postgres credential handle
    # (CAP-DATABASE-RUNTIME-CUTOVER, design "Credential convergence").
    # Postgres injection is owned by the `odoo_forge_postgres_docker`
    # adapter's `PostgreSQLSecretInjection`, never by `postgres.secret_env`.
    postgres_credentials: CredentialHandle | None = None


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
    postgres_credentials: CredentialHandle | None = None,
) -> BackendPlan:
    """Compute a `BackendPlan` from validated evidence. Pure, zero I/O."""
    odoo_http_port = None
    odoo_bind_host = DEFAULT_ODOO_BIND_HOST
    if manifest.backend is not None and manifest.backend.odoo is not None:
        odoo_http_port = manifest.backend.odoo.http_port
        odoo_bind_host = manifest.backend.odoo.bind_host

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
        # Postgres credential injection is owned by the adapter's
        # `PostgreSQLSecretInjection`; the handle rides `postgres_credentials`
        # below, never `secret_env` (design "Credential convergence").
        secret_env={},
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
            # Manifest-derived addons_path precedence, consumed by
            # entrypoint.sh's build_addons_path (honors `mount_priority`). The
            # entrypoint still appends /opt/odoo/addons last and falls back to
            # its own default scan when this is unset.
            "FORGE_ADDONS_PATH_ORDER": ",".join(
                str(root) for root in ordered_addons_roots(manifest)
            ),
        },
        secret_env={"DB_PASSWORD": credentials.odoo_db_password} if credentials is not None else {},
        mounts=mounts,
        labels=_labels(project, instance, role="odoo"),
        volumes=[filestore_volume],
        bind_host=odoo_bind_host,
        ports={"8069": odoo_http_port, "8072": None},
    )

    return BackendPlan(
        network=NetworkSpec(name=network_name, labels=_labels(project, instance)),
        volumes=[pgdata_volume, filestore_volume],
        postgres=postgres_spec,
        odoo=odoo_spec,
        postgres_credentials=postgres_credentials,
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
