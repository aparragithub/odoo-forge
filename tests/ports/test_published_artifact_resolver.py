from dataclasses import FrozenInstanceError

import pytest

from odoo_forge.manifest.artifacts import PublishedArtifactResolution
from odoo_forge.ports.published_artifact_resolver import PublishedArtifactResolver


class _FakePublishedArtifactResolver:
    def resolve(self, source: str, version: str) -> PublishedArtifactResolution:
        return PublishedArtifactResolution(
            source=source,
            version=version,
            digest="sha256:" + "a" * 64,
        )


def test_conforming_resolver_returns_an_immutable_published_resolution() -> None:
    resolver = _FakePublishedArtifactResolver()

    resolution = resolver.resolve("registry://example/odoo-ee", "19.0")

    assert isinstance(resolver, PublishedArtifactResolver)
    assert resolution == PublishedArtifactResolution(
        source="registry://example/odoo-ee",
        version="19.0",
        digest="sha256:" + "a" * 64,
    )
    with pytest.raises(FrozenInstanceError):
        resolution.digest = "sha256:" + "b" * 64  # type: ignore[misc]
