"""Pure-domain anonymization policy: rule selectors and the fixed v1 mask-strategy vocabulary.

This module mirrors `credentials/materialization.py`'s split between a pure
step and its adapter-owned implementation: it never touches bytes or artifact
content. It only describes WHICH `table`/`column` selector gets WHICH mask
strategy. The byte-level implementation of a mask strategy (the
`MaskTransform` port, see `apply.py`) is owned by the adapter package and is
out of scope here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from odoo_forge.data_artifacts.types import _ArtifactValue, require_safe_opaque_identifier


class MaskStrategy(StrEnum):
    """Fixed v1 vocabulary for how a selected table/column value is masked."""

    REDACT = "redact"
    HASH = "hash"
    NULLIFY = "nullify"
    STATIC_REPLACE = "static_replace"


class AnonymizationRule(_ArtifactValue):
    """A pure selector (`table`, `column`) bound to one `mask_strategy`."""

    table: str
    column: str
    mask_strategy: MaskStrategy
    static_value: str | None = None

    @field_validator("table", "column")
    @classmethod
    def require_safe_selector(cls, value: str) -> str:
        return require_safe_opaque_identifier(value, "anonymization selector")

    @model_validator(mode="after")
    def require_static_value_matches_strategy(self) -> AnonymizationRule:
        if self.mask_strategy is MaskStrategy.STATIC_REPLACE and not self.static_value:
            raise ValueError("static_replace rules require a static_value")
        if self.mask_strategy is not MaskStrategy.STATIC_REPLACE and self.static_value is not None:
            raise ValueError("static_value is only allowed for static_replace rules")
        return self


class AnonymizationPolicy(_ArtifactValue):
    """An ordered, single v1 collection of `AnonymizationRule`, keyed by table/column.

    Per-environment policy tiers (QA vs preprod) are explicitly out of scope
    for v1 and deferred to SP-DATA-ENVIRONMENTS; exactly one policy applies
    uniformly regardless of target.
    """

    rules: tuple[AnonymizationRule, ...] = ()

    @model_validator(mode="after")
    def require_unique_selectors(self) -> AnonymizationPolicy:
        seen: set[tuple[str, str]] = set()
        for rule in self.rules:
            key = (rule.table, rule.column)
            if key in seen:
                raise ValueError(f"duplicate anonymization rule for {rule.table}.{rule.column}")
            seen.add(key)
        return self

    def rule_for(self, table: str, column: str) -> AnonymizationRule | None:
        """Return the rule selecting `table`/`column`, or None if unselected."""
        for rule in self.rules:
            if rule.table == table and rule.column == column:
                return rule
        return None


__all__ = ["AnonymizationPolicy", "AnonymizationRule", "MaskStrategy"]
