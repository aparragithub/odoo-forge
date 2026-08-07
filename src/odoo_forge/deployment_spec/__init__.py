"""Provider-neutral deployment specification contract."""

from odoo_forge.deployment_spec.types import (
    DeploymentSpec,
    ExposureIntent,
    OdooRuntimeIntent,
    RequirementPolicy,
    RouteProtocol,
)

__all__ = [
    "DeploymentSpec",
    "ExposureIntent",
    "OdooRuntimeIntent",
    "RequirementPolicy",
    "RouteProtocol",
]
