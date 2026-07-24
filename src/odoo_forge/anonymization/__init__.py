"""Pure-domain anonymization: policy vocabulary and the apply step."""

from odoo_forge.anonymization.apply import (
    AnonymizationOutcome,
    MaskTransform,
    apply_anonymization,
    record_anonymization_exception,
)
from odoo_forge.anonymization.policy import AnonymizationPolicy, AnonymizationRule, MaskStrategy

__all__ = [
    "AnonymizationOutcome",
    "AnonymizationPolicy",
    "AnonymizationRule",
    "MaskStrategy",
    "MaskTransform",
    "apply_anonymization",
    "record_anonymization_exception",
]
