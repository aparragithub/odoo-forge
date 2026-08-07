"""Provider-neutral, immutable deployment intent for managed Odoo instances."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from odoo_forge.instance_registry.types import InstancePointer
from odoo_forge.resource_ownership.types import ResourceRef


class _DeploymentValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class RequirementPolicy(StrEnum):
    """Whether a declared exposure concern is required or disabled."""

    DISABLED = "disabled"
    REQUIRED = "required"


class RouteProtocol(StrEnum):
    """Protocol declared for an exposed route."""

    HTTP = "http"
    HTTPS = "https"


class OdooRuntimeIntent(_DeploymentValue):
    """Provider-neutral Odoo runtime requirement."""

    odoo_version: str = Field(min_length=1)


class ExposureIntent(_DeploymentValue):
    """Declarative route, DNS, and TLS outcome for a public instance."""

    hostname: str = Field(min_length=1)
    protocol: RouteProtocol
    dns: RequirementPolicy
    tls: RequirementPolicy

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.protocol is RouteProtocol.HTTPS and self.tls is RequirementPolicy.DISABLED:
            raise ValueError("HTTPS exposure requires TLS")
        if self.protocol is RouteProtocol.HTTP and self.tls is RequirementPolicy.REQUIRED:
            raise ValueError("HTTP exposure cannot require TLS")
        return self


class DeploymentSpec(_DeploymentValue):
    """Immutable desired deployment state for one managed Odoo instance."""

    pointer: InstancePointer
    resource: ResourceRef
    runtime: OdooRuntimeIntent
    exposure: ExposureIntent | None = None


__all__ = [
    "DeploymentSpec",
    "ExposureIntent",
    "OdooRuntimeIntent",
    "RequirementPolicy",
    "RouteProtocol",
]
