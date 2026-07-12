"""Validation for the outputs required by a successful catalog resolution."""

from odoo_forge.project_catalog.models import CatalogRecord


def invalid_required_fields(record: CatalogRecord) -> list[str]:
    """Return required outputs that catalog authority did not materialize."""
    missing: list[str] = []
    if record.manifest_ref is None:
        missing.append("manifest_ref")
    if record.source_context is None:
        missing.append("source_context")
    if record.defaults.data_policy is None:
        missing.append("data_policy_default")
    if record.defaults.target is None:
        missing.append("target_default")
    return missing


__all__ = ["invalid_required_fields"]
