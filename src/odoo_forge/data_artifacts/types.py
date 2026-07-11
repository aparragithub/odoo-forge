"""Opaque references owned by the data-artifact capability."""

from typing import NewType

DataArtifactRef = NewType("DataArtifactRef", str)


__all__ = ["DataArtifactRef"]
