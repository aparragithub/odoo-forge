import json
from typing import Any, cast

import pytest
from pydantic import ValidationError

from odoo_forge.deployment_spec import (
    DeploymentSpec,
    ExposureIntent,
    OdooRuntimeIntent,
    RequirementPolicy,
    RouteProtocol,
)
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


def _runtime(version: str = "17.0") -> OdooRuntimeIntent:
    return OdooRuntimeIntent(odoo_version=version)


def _exposure(
    *,
    protocol: RouteProtocol = RouteProtocol.HTTPS,
    dns: RequirementPolicy = RequirementPolicy.REQUIRED,
    tls: RequirementPolicy = RequirementPolicy.REQUIRED,
) -> ExposureIntent:
    return ExposureIntent(
        hostname="qa.example.test",
        protocol=protocol,
        dns=dns,
        tls=tls,
    )


def _spec(*, exposure: ExposureIntent | None = None) -> DeploymentSpec:
    return DeploymentSpec(
        pointer=_pointer(),
        resource=_resource(),
        runtime=_runtime(),
        exposure=exposure,
    )


def test_public_exports_are_exact_and_reusable() -> None:
    import odoo_forge.deployment_spec as deployment_spec

    assert deployment_spec.__all__ == [
        "DeploymentSpec",
        "ExposureIntent",
        "OdooRuntimeIntent",
        "RequirementPolicy",
        "RouteProtocol",
    ]
    assert deployment_spec.DeploymentSpec is DeploymentSpec


def test_spec_reuses_canonical_identity_and_ownership_references() -> None:
    spec = _spec(exposure=_exposure())

    assert spec.pointer == _pointer()
    assert spec.resource == _resource()
    assert spec.runtime.odoo_version == "17.0"
    assert spec.exposure is not None
    assert spec.exposure.hostname == "qa.example.test"
    assert spec.exposure.protocol is RouteProtocol.HTTPS


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (DeploymentSpec, {"resource": _resource(), "runtime": _runtime()}),
        (OdooRuntimeIntent, {}),
        (ExposureIntent, {"protocol": RouteProtocol.HTTPS}),
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
        DeploymentSpec(
            pointer=_pointer(),
            resource=_resource(),
            runtime=_runtime(),
            container="docker-container",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        OdooRuntimeIntent(odoo_version="17.0", network="private")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ExposureIntent(
            hostname="qa.example.test",
            protocol=RouteProtocol.HTTPS,
            dns=RequirementPolicy.REQUIRED,
            tls=RequirementPolicy.REQUIRED,
            certificate="managed",  # type: ignore[call-arg]
        )


def test_runtime_version_and_hostname_reject_empty_values() -> None:
    with pytest.raises(ValidationError):
        OdooRuntimeIntent(odoo_version="")
    with pytest.raises(ValidationError):
        ExposureIntent(
            hostname="",
            protocol=RouteProtocol.HTTP,
            dns=RequirementPolicy.DISABLED,
            tls=RequirementPolicy.DISABLED,
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
        (RouteProtocol.HTTPS, RequirementPolicy.REQUIRED, RequirementPolicy.DISABLED),
        (RouteProtocol.HTTP, RequirementPolicy.REQUIRED, RequirementPolicy.REQUIRED),
    ],
)
def test_exposure_rejects_contradictory_tls_policies(
    protocol: RouteProtocol, dns: RequirementPolicy, tls: RequirementPolicy
) -> None:
    with pytest.raises(ValidationError):
        _exposure(protocol=protocol, dns=dns, tls=tls)


def test_disabled_internal_http_policy_is_valid() -> None:
    exposure = _exposure(
        protocol=RouteProtocol.HTTP,
        dns=RequirementPolicy.DISABLED,
        tls=RequirementPolicy.DISABLED,
    )

    assert exposure.protocol is RouteProtocol.HTTP
    assert exposure.dns is RequirementPolicy.DISABLED
    assert exposure.tls is RequirementPolicy.DISABLED


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
    assert DeploymentSpec.model_validate_json(first) == spec


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
        DeploymentSpec(
            pointer=_pointer(),
            resource=_resource(),
            runtime=_runtime(),
            **mechanic,
        )
