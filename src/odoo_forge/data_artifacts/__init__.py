"""Public contract for opaque, coherent data-artifact restore inputs."""

from odoo_forge.data_artifacts.capture import CaptureSource, DataArtifactCaptureCapability
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    DataArtifactCapability,
    DiscardOutcome,
    DiscardOutcomeCode,
    RestoreReadiness,
    RestoreSetComponent,
    RestoreSetManifest,
    ValidationFailureCode,
)
from odoo_forge.data_artifacts.types import DataArtifactRef

__all__ = [
    "ArtifactComponentKind",
    "ArtifactDigest",
    "CaptureSource",
    "DataArtifactCapability",
    "DataArtifactCaptureCapability",
    "DataArtifactRef",
    "DiscardOutcome",
    "DiscardOutcomeCode",
    "RestoreReadiness",
    "RestoreSetComponent",
    "RestoreSetManifest",
    "ValidationFailureCode",
]
