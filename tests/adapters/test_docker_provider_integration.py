"""Opt-in real-Docker lifecycle evidence for ``DockerBackendProvider``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from odoo_forge.backend.plan import (
    BackendPlan,
    ContainerSpec,
    NetworkSpec,
    VolumeSpec,
    plan_backend,
)
from odoo_forge.credentials.types import BackendCredentialBindings, CredentialHandle
from odoo_forge.manifest.schema import Client, Manifest
from odoo_forge.manifest.state import MaterializedState
from odoo_forge_docker.credential_injection import SopsEnvFileInjector
from odoo_forge_docker.provider import DockerBackendProvider

pytestmark = pytest.mark.integration

_FACTORY_SOURCE = "https://github.com/aparragithub/odoo-forge"
_FACTORY_VERSION = "19.0"


def _docker(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *argv], capture_output=True, text=True, check=False)


def _require_docker() -> None:
    try:
        result = _docker(["info", "--format", "{{.ServerVersion}}"])
    except FileNotFoundError:
        pytest.skip("Docker prerequisite unavailable: executable not found")
    if result.returncode != 0:
        pytest.skip("Docker prerequisite unavailable: daemon is unreachable")


def _factory_image() -> str:
    image = os.environ.get("ODOO_FORGE_TEST_ODOO_IMAGE")
    assert image, "ODOO_FORGE_TEST_ODOO_IMAGE must select a project-factory Odoo image"

    inspected = _docker(["image", "inspect", image])
    assert inspected.returncode == 0, f"selected Odoo image is unavailable: {image}"
    metadata = json.loads(inspected.stdout)[0]
    labels = _inspect_labels(metadata)
    assert labels.get("org.opencontainers.image.source") == _FACTORY_SOURCE
    assert labels.get("org.opencontainers.image.version") == _FACTORY_VERSION
    assert labels.get("org.opencontainers.image.revision"), (
        "factory image revision label is required"
    )
    return _immutable_digest(metadata, image)


def _inspect_labels(metadata: object) -> dict[str, str]:
    assert isinstance(metadata, dict), "selected Odoo image metadata is invalid"
    config = metadata.get("Config")
    assert isinstance(config, dict), "selected Odoo image config is invalid"
    labels = config.get("Labels")
    assert isinstance(labels, dict), "selected Odoo image labels are invalid"
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in labels.items())
    return cast(dict[str, str], labels)


def _immutable_digest(metadata: object, image: str) -> str:
    assert isinstance(metadata, dict), "selected Odoo image metadata is invalid"
    digests = metadata.get("RepoDigests")
    assert isinstance(digests, list), "selected Odoo image has no immutable digest"
    repository, separator, tag = image.partition("@")
    if not separator and ":" in repository.rsplit("/", 1)[-1]:
        repository = repository.rsplit(":", 1)[0]
    prefix = f"{repository}@sha256:"
    digest = next(
        (value for value in digests if isinstance(value, str) and value.startswith(prefix)),
        None,
    )
    assert digest, "selected Odoo image has no matching immutable digest"
    return digest


def test_cleanup_ignores_already_absent_owned_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = cast(
        BackendPlan,
        SimpleNamespace(
            postgres=SimpleNamespace(name="owned-postgres"),
            odoo=SimpleNamespace(name="owned-odoo"),
            network=SimpleNamespace(name="owned-network"),
            volumes=[
                SimpleNamespace(name="owned-pgdata"),
                SimpleNamespace(name="owned-filestore"),
            ],
        ),
    )

    monkeypatch.setattr(
        sys.modules[__name__],
        "_docker",
        lambda argv: subprocess.CompletedProcess(
            argv, 1, stderr=f"Error response from daemon: {argv[-1]} not found"
        ),
    )

    assert _cleanup(plan) == []


def test_cleanup_retains_true_owned_cleanup_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = cast(
        BackendPlan,
        SimpleNamespace(
            postgres=SimpleNamespace(name="owned-postgres"),
            odoo=SimpleNamespace(name="owned-odoo"),
            network=SimpleNamespace(name="owned-network"),
            volumes=[SimpleNamespace(name="owned-pgdata")],
        ),
    )

    monkeypatch.setattr(
        sys.modules[__name__],
        "_docker",
        lambda argv: subprocess.CompletedProcess(argv, 1, stderr="permission denied"),
    )

    assert _cleanup(plan) == [
        "rm -f owned-postgres",
        "rm -f owned-odoo",
        "rm -f owned-odoo-bootstrap",
        "network rm owned-network",
        "volume rm owned-pgdata",
    ]


def test_cleanup_retains_unrelated_not_found_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = cast(
        BackendPlan,
        SimpleNamespace(
            postgres=SimpleNamespace(name="owned-postgres"),
            odoo=SimpleNamespace(name="owned-odoo"),
            network=SimpleNamespace(name="owned-network"),
            volumes=[],
        ),
    )
    monkeypatch.setattr(
        sys.modules[__name__],
        "_docker",
        lambda argv: subprocess.CompletedProcess(argv, 1, stderr="plugin not found"),
    )

    assert len(_cleanup(plan)) == 4


def test_residuals_reports_failed_docker_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = cast(
        BackendPlan,
        SimpleNamespace(network=SimpleNamespace(labels={"com.odoo-forge.instance": "owned"})),
    )
    monkeypatch.setattr(
        sys.modules[__name__],
        "_docker",
        lambda argv: subprocess.CompletedProcess(argv, 1, stdout=""),
    )

    assert _residuals(plan) == [
        "containers query failed",
        "networks query failed",
        "volumes query failed",
    ]


def test_factory_image_resolves_validated_tag_to_immutable_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = "ghcr.io/aparragithub/odoo-ce:19"
    digest = "ghcr.io/aparragithub/odoo-ce@sha256:abcdef"
    metadata = {
        "Config": {
            "Labels": {
                "org.opencontainers.image.source": _FACTORY_SOURCE,
                "org.opencontainers.image.version": _FACTORY_VERSION,
                "org.opencontainers.image.revision": "revision",
            }
        },
        "RepoDigests": [digest],
    }
    monkeypatch.setenv("ODOO_FORGE_TEST_ODOO_IMAGE", selected)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_docker",
        lambda argv: subprocess.CompletedProcess(argv, 0, stdout=json.dumps([metadata])),
    )

    assert _factory_image() == digest


def _plan(tmp_path: Path, image: str, secret: str) -> BackendPlan:
    identity = f"real-{uuid.uuid4().hex[:12]}"
    manifest = Manifest(
        name=f"integration-{identity}",
        odoo_version=_FACTORY_VERSION,
        edition="community",
        client=Client(addons_path=tmp_path),
    )
    credentials = BackendCredentialBindings(
        postgres_password=CredentialHandle("integration/postgres"),
        odoo_db_password=CredentialHandle("integration/odoo"),
    )
    plan = plan_backend(
        manifest,
        MaterializedState(),
        instance=identity,
        odoo_image=image,
        credentials=credentials,
    ).model_copy(deep=True)
    plan.odoo.mounts = []
    assert plan.postgres.image == "postgres:16"
    assert plan.odoo.ports == {"8069": None, "8072": None}
    resources: tuple[NetworkSpec | VolumeSpec | ContainerSpec, ...] = (
        plan.network,
        *plan.volumes,
        plan.postgres,
        plan.odoo,
    )
    assert all(_resource_labels(spec)["com.odoo-forge.instance"] == identity for spec in resources)
    assert secret not in repr(plan)
    return plan


def _resource_labels(resource: NetworkSpec | VolumeSpec | ContainerSpec) -> dict[str, str]:
    return resource.labels


def _cleanup(plan: BackendPlan) -> list[str]:
    errors: list[str] = []
    for argv in (
        ["rm", "-f", plan.postgres.name],
        ["rm", "-f", plan.odoo.name],
        ["rm", "-f", f"{plan.odoo.name}-bootstrap"],
        ["network", "rm", plan.network.name],
        *(["volume", "rm", volume.name] for volume in plan.volumes),
    ):
        result = _docker(argv)
        absent = f"{argv[-1]} not found" in result.stderr.lower()
        if result.returncode != 0 and not absent:
            errors.append(" ".join(argv[:3]))
    return errors


def _residuals(plan: BackendPlan) -> list[str]:
    instance = plan.network.labels["com.odoo-forge.instance"]
    label = f"com.odoo-forge.instance={instance}"
    checks = {
        "containers": ["ps", "-aq", "--filter", f"label={label}"],
        "networks": ["network", "ls", "-q", "--filter", f"label={label}"],
        "volumes": ["volume", "ls", "-q", "--filter", f"label={label}"],
    }
    residuals: list[str] = []
    for name, argv in checks.items():
        result = _docker(argv)
        if result.returncode != 0:
            residuals.append(f"{name} query failed")
        elif result.stdout.strip():
            residuals.append(name)
    return residuals


def _container_exists(name: str) -> bool:
    return _docker(["container", "inspect", name]).returncode == 0


def _network_exists(name: str) -> bool:
    return _docker(["network", "inspect", name]).returncode == 0


def _volume_exists(name: str) -> bool:
    return _docker(["volume", "inspect", name]).returncode == 0


def test_run_status_stop_round_trip_against_real_daemon(tmp_path: Path) -> None:
    """Exercise the canonical lifecycle without making the default suite use Docker."""
    _require_docker()
    image = _factory_image()
    secret = uuid.uuid4().hex
    plan = _plan(tmp_path, image, secret)
    values = {
        CredentialHandle("integration/postgres"): secret,
        CredentialHandle("integration/odoo"): secret,
    }
    provider = DockerBackendProvider(credential_injector=SopsEnvFileInjector(values.__getitem__))

    try:
        ref = provider.run(plan)
        status = provider.status(ref)
        assert status.postgres.running and status.odoo.running
        assert status.odoo.ready

        ports = json.loads(_docker(["container", "inspect", plan.odoo.name]).stdout)[0][
            "NetworkSettings"
        ]["Ports"]
        assert ports["8069/tcp"][0]["HostPort"]
        assert ports["8072/tcp"][0]["HostPort"]

        provider.stop(ref)
        assert not _container_exists(plan.postgres.name)
        assert not _container_exists(plan.odoo.name)
        assert not _network_exists(plan.network.name)
        assert all(_volume_exists(volume.name) for volume in plan.volumes)
    except Exception as exc:
        assert secret not in str(exc)
        raise
    finally:
        cleanup_errors = _cleanup(plan)
        assert not cleanup_errors, f"owned cleanup failed: {cleanup_errors}"
        assert not _residuals(plan), "owned Docker resources leaked"
