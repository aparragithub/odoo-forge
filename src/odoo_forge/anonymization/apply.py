"""Pure anonymization step between capture and delivery.

Applies an `AnonymizationPolicy` to a captured `RestoreSetManifest`, producing
a new manifest plus a `RedactedEvidence` audit record. Byte-level masking is
delegated to an injected `MaskTransform` port; the Postgres implementation of
that port lives in the adapter package (out of scope here) — this module
never touches bytes directly, mirroring `credentials/materialization.py`'s
split between a pure step and its adapter-owned implementation.

Default behavior is anonymize-by-default: `apply_anonymization` always
anonymizes the database component and records `event="anonymization_applied"`.
Raw (non-anonymized) delivery is a distinct, explicit exception path recorded
via `record_anonymization_exception`, which leaves the manifest unchanged and
emits `event="anonymization_exception"`. Enforcing that raw delivery is
refused unless a matching exception checkpoint exists for the operation's
`lineage_id` is the delivery gate's responsibility (coordinator, PR3) — this
module only produces the audit-safe evidence for either path.
"""

from __future__ import annotations

from collections.abc import Callable

from odoo_forge.anonymization.policy import AnonymizationPolicy, AnonymizationRule
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.types import _ArtifactValue
from odoo_forge.durable_operations.types import RedactedEvidence

MaskTransform = Callable[[RestoreSetComponent, tuple[AnonymizationRule, ...]], RestoreSetComponent]


class AnonymizationOutcome(_ArtifactValue):
    """A (possibly anonymized) manifest paired with its audit evidence."""

    manifest: RestoreSetManifest
    evidence: RedactedEvidence


def apply_anonymization(
    manifest: RestoreSetManifest,
    policy: AnonymizationPolicy,
    mask_transform: MaskTransform,
) -> AnonymizationOutcome:
    """Anonymize `manifest`'s database component per `policy` (the default path)."""
    anonymized_components = tuple(
        mask_transform(component, policy.rules)
        if component.kind is ArtifactComponentKind.DATABASE
        else component
        for component in manifest.components
    )
    anonymized_manifest = RestoreSetManifest(
        restore_set_id=manifest.restore_set_id,
        lineage_id=manifest.lineage_id,
        components=anonymized_components,
    )
    evidence = RedactedEvidence(
        event="anonymization_applied",
        summary="anonymization policy applied before delivery",
        references=(manifest.lineage_id,),
    )
    return AnonymizationOutcome(manifest=anonymized_manifest, evidence=evidence)


def record_anonymization_exception(
    manifest: RestoreSetManifest, reason: str
) -> AnonymizationOutcome:
    """Record an audited grant to deliver `manifest` raw, unchanged, without anonymization."""
    evidence = RedactedEvidence(
        event="anonymization_exception",
        summary=reason,
        references=(manifest.lineage_id,),
    )
    return AnonymizationOutcome(manifest=manifest, evidence=evidence)


__all__ = [
    "AnonymizationOutcome",
    "MaskTransform",
    "apply_anonymization",
    "record_anonymization_exception",
]
