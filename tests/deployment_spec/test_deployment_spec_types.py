import json
from typing import Any, cast

import pytest
from pydantic import ValidationError

import odoo_forge.deployment_spec as deployment_spec
from odoo_forge.instance_registry import InstanceId, InstancePointer
from odoo_forge.resource_ownership import ResourceOwnership, ResourceRef
from odoo_forge.tenancy import ProjectScope, TenantId


def _pointer() -> InstancePointer:
    return InstancePointer(
        scope=ProjectScope(tenant=TenantId(value="tenant-1"), project_id="project-1"),
        instance_id=InstanceId(value="qa"),
    )


def _resource() -> ResourceRef:
    return ResourceRef(
        identifier="odoo-qa",
        resource_kind="odoo_instance",
        ownership=ResourceOwnership.CREATED,
    )


def _runtime(version: str = "17.0") -> deployment_spec.OdooRuntimeIntent:
    return deployment_spec.OdooRuntimeIntent(odoo_version=version)


def _exposure(
    *,
    protocol: deployment_spec.RouteProtocol = deployment_spec.RouteProtocol.HTTPS,
    dns: deployment_spec.RequirementPolicy = deployment_spec.RequirementPolicy.REQUIRED,
    tls: deployment_spec.RequirementPolicy = deployment_spec.RequirementPolicy.REQUIRED,
) -> deployment_spec.ExposureIntent:
    return deployment_spec.ExposureIntent(
        hostname="qa.example.test",
        protocol=protocol,
        dns=dns,
        tls=tls,
    )


def _spec(
    *, exposure: deployment_spec.ExposureIntent | None = None
) -> deployment_spec.DeploymentSpec:
    return deployment_spec.DeploymentSpec(
        pointer=_pointer(),
        resource=_resource(),
        runtime=_runtime(),
        exposure=exposure,
    )


def test_public_exports_are_exact_and_reusable() -> None:
    assert deployment_spec.__all__ == [
        "DeploymentSpec",
        "ExposureIntent",
        "OdooRuntimeIntent",
        "RequirementPolicy",
        "RouteProtocol",
    ]
    assert deployment_spec.DeploymentSpec is _spec().__class__


def test_spec_reuses_canonical_identity_and_ownership_references() -> None:
    spec = _spec(exposure=_exposure())

    assert spec.pointer == _pointer()
    assert spec.resource == _resource()
    assert spec.runtime.odoo_version == "17.0"
    assert spec.exposure is not None
    assert spec.exposure.hostname == "qa.example.test"
    assert spec.exposure.protocol is deployment_spec.RouteProtocol.HTTPS


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (deployment_spec.DeploymentSpec, {"resource": _resource(), "runtime": _runtime()}),
        (deployment_spec.OdooRuntimeIntent, {}),
        (deployment_spec.ExposureIntent, {"protocol": deployment_spec.RouteProtocol.HTTPS}),
    ],
)
def test_required_contract_fields_are_not_optional(
    model: type[Any], kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_values_are_frozen_and_forbid_unknown_fields_at_every_contract_level() -> None:
    spec = _spec(exposure=_exposure())

    with pytest.raises(ValidationError):
        cast(Any, spec).runtime = _runtime("18.0")
    with pytest.raises(ValidationError):
        cast(Any, spec.runtime).odoo_version = "18.0"
    with pytest.raises(ValidationError):
        deployment_spec.DeploymentSpec(
            pointer=_pointer(),
            resource=_resource(),
            runtime=_runtime(),
            container="docker-container",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        deployment_spec.OdooRuntimeIntent(  # type: ignore[call-arg]
            odoo_version="17.0", network="private"
        )
    with pytest.raises(ValidationError):
        deployment_spec.ExposureIntent(
            hostname="qa.example.test",
            protocol=deployment_spec.RouteProtocol.HTTPS,
            dns=deployment_spec.RequirementPolicy.REQUIRED,
            tls=deployment_spec.RequirementPolicy.REQUIRED,
            certificate="managed",  # type: ignore[call-arg]
        )


def test_runtime_version_and_hostname_reject_empty_values() -> None:
    with pytest.raises(ValidationError):
        deployment_spec.OdooRuntimeIntent(odoo_version="")
    with pytest.raises(ValidationError):
        deployment_spec.ExposureIntent(
            hostname="",
            protocol=deployment_spec.RouteProtocol.HTTP,
            dns=deployment_spec.RequirementPolicy.DISABLED,
            tls=deployment_spec.RequirementPolicy.DISABLED,
        )


def test_public_https_intent_records_outcomes_without_provider_mechanics() -> None:
    exposure = _exposure()

    assert exposure.model_dump() == {
        "hostname": "qa.example.test",
        "protocol": "https",
        "dns": "required",
        "tls": "required",
    }
    assert set(exposure.model_dump()) == {"hostname", "protocol", "dns", "tls"}


def test_internal_instance_has_no_implicit_public_exposure() -> None:
    spec = _spec()

    assert spec.exposure is None
    assert spec.model_dump()["exposure"] is None


@pytest.mark.parametrize(
    ("protocol", "dns", "tls"),
    [
        (
            deployment_spec.RouteProtocol.HTTPS,
            deployment_spec.RequirementPolicy.REQUIRED,
            deployment_spec.RequirementPolicy.DISABLED,
        ),
        (
            deployment_spec.RouteProtocol.HTTP,
            deployment_spec.RequirementPolicy.REQUIRED,
            deployment_spec.RequirementPolicy.REQUIRED,
        ),
    ],
)
def test_exposure_rejects_contradictory_tls_policies(
    protocol: deployment_spec.RouteProtocol,
    dns: deployment_spec.RequirementPolicy,
    tls: deployment_spec.RequirementPolicy,
) -> None:
    with pytest.raises(ValidationError):
        _exposure(protocol=protocol, dns=dns, tls=tls)


def test_disabled_internal_http_policy_is_valid() -> None:
    exposure = _exposure(
        protocol=deployment_spec.RouteProtocol.HTTP,
        dns=deployment_spec.RequirementPolicy.DISABLED,
        tls=deployment_spec.RequirementPolicy.DISABLED,
    )

    assert exposure.protocol is deployment_spec.RouteProtocol.HTTP
    assert exposure.dns is deployment_spec.RequirementPolicy.DISABLED
    assert exposure.tls is deployment_spec.RequirementPolicy.DISABLED


def test_serialization_is_deterministic_provider_neutral_and_round_trips() -> None:
    spec = _spec(exposure=_exposure())

    first = spec.model_dump_json()
    assert first == spec.model_dump_json()
    assert json.loads(first) == {
        "pointer": {
            "scope": {"tenant": {"value": "tenant-1"}, "project_id": "project-1"},
            "instance_id": {"value": "qa"},
        },
        "resource": {
            "identifier": "odoo-qa",
            "resource_kind": "odoo_instance",
            "ownership": "created",
        },
        "runtime": {"odoo_version": "17.0"},
        "exposure": {
            "hostname": "qa.example.test",
            "protocol": "https",
            "dns": "required",
            "tls": "required",
        },
    }
    assert deployment_spec.DeploymentSpec.model_validate_json(first) == spec


@pytest.mark.parametrize(
    "mechanic",
    [
        {"network": "private"},
        {"volume": "data"},
        {"port": 8069},
        {"ingress": "nginx"},
        {"cloud_provider": "aws"},
        {"adapter_operation": "create"},
    ],
)
def test_provider_mechanics_are_rejected(mechanic: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        deployment_spec.DeploymentSpec(
            pointer=_pointer(),
            resource=_resource(),
            runtime=_runtime(),
            **mechanic,
        )
