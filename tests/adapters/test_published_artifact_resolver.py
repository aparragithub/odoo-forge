import pytest

from odoo_forge.image_registry.errors import RegistryImageNotFoundError, RegistryUnavailableError
from odoo_forge.image_registry.types import ImageDigestRef, ImageRef
from odoo_forge.manifest.artifacts import (
    PublishedArtifactDigestMissingError,
    PublishedArtifactNotFoundError,
    PublishedArtifactResolutionError,
)
from odoo_forge_registry.published_artifact_resolver import PublishedArtifactRegistryResolver


class _FakeRegistry:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls: list[str] = []

    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef:
        self.calls.append(str(ref))
        if isinstance(self.result, Exception):
            raise self.result
        return ImageDigestRef(self.result)


def test_resolver_maps_registry_source_and_returns_immutable_digest() -> None:
    registry = _FakeRegistry("ghcr.io/example/odoo-ee@sha256:" + "a" * 64)

    resolution = PublishedArtifactRegistryResolver(registry).resolve(
        "registry://example/odoo-ee", "19.0"
    )

    assert registry.calls == ["ghcr.io/example/odoo-ee:19.0"]
    assert resolution.source == "registry://example/odoo-ee"
    assert resolution.version == "19.0"
    assert resolution.digest == "sha256:" + "a" * 64


def test_resolver_translates_not_found_and_missing_digest_failures() -> None:
    not_found = PublishedArtifactRegistryResolver(
        _FakeRegistry(RegistryImageNotFoundError("ghcr.io/example/odoo-ee:19.0"))
    )
    missing_digest = PublishedArtifactRegistryResolver(
        _FakeRegistry("ghcr.io/example/odoo-ee:19.0")
    )

    with pytest.raises(PublishedArtifactNotFoundError):
        not_found.resolve("registry://example/odoo-ee", "19.0")
    with pytest.raises(PublishedArtifactDigestMissingError):
        missing_digest.resolve("registry://example/odoo-ee", "19.0")


@pytest.mark.parametrize(
    "digest",
    ["sha256:", "sha256:" + "a" * 63, "sha256:" + "A" * 64, "sha256:" + "g" * 64],
)
def test_resolver_rejects_malformed_digest(digest: str) -> None:
    resolver = PublishedArtifactRegistryResolver(_FakeRegistry(f"ghcr.io/example/odoo-ee@{digest}"))

    with pytest.raises(PublishedArtifactDigestMissingError):
        resolver.resolve("registry://example/odoo-ee", "19.0")


def test_resolver_translates_general_registry_failure() -> None:
    resolver = PublishedArtifactRegistryResolver(
        _FakeRegistry(RegistryUnavailableError("ghcr.io/example/odoo-ee:19.0", "offline"))
    )

    with pytest.raises(PublishedArtifactResolutionError, match="offline"):
        resolver.resolve("registry://example/odoo-ee", "19.0")
