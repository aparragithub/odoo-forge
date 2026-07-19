"""Validation for the outputs required by a successful catalog resolution."""

from odoo_forge.project_catalog.models import (
    CatalogRecord,
    InvalidCatalogRecord,
    ValidatedCatalogRecord,
)


def _is_blank(value: str | None) -> bool:
    """True when a required string output is absent or whitespace-only."""
    return value is None or not value.strip()


def invalid_required_fields(record: CatalogRecord) -> list[str]:
    """Return required outputs that catalog authority did not materialize."""
    missing: list[str] = []
    if record.manifest_ref is None:
        missing.append("manifest_ref")
    if record.source_context is None:
        missing.append("source_context")
    if _is_blank(record.defaults.data_policy):
        missing.append("data_policy_default")
    if _is_blank(record.defaults.target):
        missing.append("target_default")
    return missing


def invalid_catalog_reason_code(invalid_fields: list[str]) -> str:
    """Classify invalid catalog authority with a deterministic reason code."""
    return "missing:" + "+".join(invalid_fields)


def validate_record(record: CatalogRecord) -> ValidatedCatalogRecord | InvalidCatalogRecord:
    """Prove a catalog record carries every required output, or classify why it does not."""
    manifest_ref = record.manifest_ref
    source_context = record.source_context
    data_policy = record.defaults.data_policy
    target = record.defaults.target

    if (
        manifest_ref is None
        or source_context is None
        or _is_blank(data_policy)
        or _is_blank(target)
    ):
        invalid_fields = invalid_required_fields(record)
        return InvalidCatalogRecord(
            record_id=record.record_id,
            invalid_fields=invalid_fields,
            reason_code=invalid_catalog_reason_code(invalid_fields),
        )

    return ValidatedCatalogRecord(
        record_id=record.record_id,
        manifest_ref=manifest_ref,
        source_context=source_context,
        data_policy_default=data_policy,
        target_default=target,
    )


__all__ = ["invalid_catalog_reason_code", "invalid_required_fields", "validate_record"]
