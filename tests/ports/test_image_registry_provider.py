import inspect
import typing

import pytest

from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    UnsupportedRegistryError,
)
from odoo_forge.image_registry.reference import normalize_image_reference
from odoo_forge.ports.image_registry_provider import ImageRegistryProvider


class _FakeImageRegistryProvider:
    def resolve(self, ref: str) -> str:
        return f"resolved::{ref}"

    def validate(self, ref: str) -> str:
        return ref


def test_conforming_class_satisfies_image_registry_provider_protocol() -> None:
    provider = _FakeImageRegistryProvider()

    assert isinstance(provider, ImageRegistryProvider)
    assert provider.resolve("ghcr.io/acme/app:latest") == "resolved::ghcr.io/acme/app:latest"


def test_non_conforming_class_does_not_satisfy_protocol() -> None:
    class _NotAProvider:
        pass

    assert not isinstance(_NotAProvider(), ImageRegistryProvider)


@pytest.mark.parametrize(
    ("ref", "require_digest", "expected"),
    [
        (
            "ghcr.io/acme/app:latest",
            False,
            "ghcr.io/acme/app:latest",
        ),
        (
            "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            False,
            "ghcr.io/acme/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        (
            "ghcr.io/acme/app@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            True,
            "ghcr.io/acme/app@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
    ],
)
def test_normalize_image_reference_accepts_supported_ghcr_refs(
    ref: str, require_digest: bool, expected: str
) -> None:
    assert normalize_image_reference(ref, require_digest=require_digest) == expected


def test_normalize_image_reference_rejects_unsupported_registry() -> None:
    with pytest.raises(UnsupportedRegistryError) as exc:
        normalize_image_reference("docker.io/library/nginx:latest", require_digest=False)

    assert "unsupported registry" in str(exc.value)
    assert "ghcr.io" in str(exc.value)


@pytest.mark.parametrize(
    ("ref", "require_digest"),
    [
        ("ghcr.io/acme/app", False),
        ("ghcr.io/acme/app:not valid", False),
        ("ghcr.io/acme/app:latest", True),
        ("ghcr.io/acme/app@sha256:xyz", True),
    ],
)
def test_normalize_image_reference_rejects_malformed_refs(ref: str, require_digest: bool) -> None:
    with pytest.raises(MalformedImageReferenceError):
        normalize_image_reference(ref, require_digest=require_digest)


def test_signature_conformance_per_method() -> None:
    port_localns = {"str": str}

    for name in ("resolve", "validate"):
        port_method = getattr(ImageRegistryProvider, name)
        impl_method = getattr(_FakeImageRegistryProvider, name)

        port_sig = inspect.signature(port_method)
        impl_sig = inspect.signature(impl_method)
        assert list(port_sig.parameters) == list(impl_sig.parameters)

        port_hints = typing.get_type_hints(port_method, localns=port_localns)
        impl_hints = typing.get_type_hints(impl_method)

        assert str(port_hints["ref"]) == str(impl_hints["ref"])
        assert str(port_hints["return"]) == str(impl_hints["return"])
