import inspect
import typing

import pytest

from odoo_forge.image_registry import ImageDigestRef, ImageRef, LocalImageRef
from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryPublishError,
    RegistryPullError,
    UnsupportedRegistryError,
)
from odoo_forge.image_registry.reference import (
    normalize_digest_image_reference,
    normalize_image_reference,
    normalize_publishable_image_reference,
)
from odoo_forge.ports.image_registry_provider import ImageRegistryProvider


class _FakeImageRegistryProvider:
    def publish(self, ref: ImageRef) -> ImageDigestRef:
        return ImageDigestRef(f"published::{ref}")

    def pull(self, digest: ImageDigestRef) -> LocalImageRef:
        return LocalImageRef(f"pulled::{digest}")

    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef:
        return ImageDigestRef(f"resolved::{ref}")

    def exists(self, digest: ImageDigestRef) -> bool:
        return str(digest).endswith("present")


def test_image_registry_value_types_are_re_exported() -> None:
    assert str(ImageRef("ghcr.io/acme/app:latest")) == "ghcr.io/acme/app:latest"
    assert str(ImageDigestRef("ghcr.io/acme/app@sha256:" + "a" * 64)) == (
        "ghcr.io/acme/app@sha256:" + "a" * 64
    )
    assert str(LocalImageRef("ghcr.io/acme/app@sha256:" + "b" * 64)) == (
        "ghcr.io/acme/app@sha256:" + "b" * 64
    )


@pytest.mark.parametrize(
    ("error_cls", "ref", "detail", "expected_fragment"),
    [
        (
            RegistryPublishError,
            "ghcr.io/acme/app:latest",
            "push failed: denied",
            "cannot publish",
        ),
        (
            RegistryPullError,
            "ghcr.io/acme/app@sha256:" + "d" * 64,
            "pull failed: unauthorized",
            "cannot prefetch",
        ),
    ],
)
def test_registry_publish_and_pull_errors_render_clear_messages(
    error_cls: type[Exception], ref: str, detail: str, expected_fragment: str
) -> None:
    error: typing.Any = error_cls(ref, detail)

    assert ref in str(error)
    assert detail in str(error)
    assert expected_fragment in str(error)
    assert error.ref == ref
    assert error.detail == detail


def test_conforming_class_satisfies_image_registry_provider_protocol() -> None:
    provider = _FakeImageRegistryProvider()

    assert isinstance(provider, ImageRegistryProvider)
    assert provider.publish(ImageRef("ghcr.io/acme/app:latest")) == (
        "published::ghcr.io/acme/app:latest"
    )
    assert provider.pull(ImageDigestRef("ghcr.io/acme/app@sha256:" + "a" * 64)) == (
        "pulled::ghcr.io/acme/app@sha256:" + "a" * 64
    )
    assert provider.resolve_digest(ImageRef("ghcr.io/acme/app:latest")) == (
        "resolved::ghcr.io/acme/app:latest"
    )
    assert provider.exists(ImageDigestRef("ghcr.io/acme/app@sha256:" + "p" * 7 + "resent"))


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


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("ghcr.io/acme/app:latest", "ghcr.io/acme/app:latest"),
        ("ghcr.io/acme/app:1.2.3", "ghcr.io/acme/app:1.2.3"),
    ],
)
def test_normalize_publishable_image_reference_accepts_supported_ghcr_refs(
    ref: str, expected: str
) -> None:
    assert normalize_publishable_image_reference(ref) == expected


def test_normalize_publishable_image_reference_rejects_digest_refs() -> None:
    with pytest.raises(MalformedImageReferenceError) as exc:
        normalize_publishable_image_reference("ghcr.io/acme/app@sha256:" + "d" * 64)

    assert "publishable" in str(exc.value).lower()


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (
            "ghcr.io/acme/app@sha256:" + "b" * 64,
            "ghcr.io/acme/app@sha256:" + "b" * 64,
        ),
        (
            "ghcr.io/acme/tool@sha256:" + "c" * 64,
            "ghcr.io/acme/tool@sha256:" + "c" * 64,
        ),
    ],
)
def test_normalize_digest_image_reference_accepts_supported_ghcr_refs(
    ref: str, expected: str
) -> None:
    assert normalize_digest_image_reference(ref) == expected


def test_normalize_image_reference_rejects_unsupported_registry() -> None:
    with pytest.raises(UnsupportedRegistryError):
        normalize_image_reference("docker.io/library/nginx:latest", require_digest=False)


def test_normalize_publishable_image_reference_rejects_unsupported_registry() -> None:
    with pytest.raises(UnsupportedRegistryError) as exc:
        normalize_publishable_image_reference("docker.io/library/nginx:latest")

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


@pytest.mark.parametrize(
    "ref",
    [
        "ghcr.io/acme/app",
        "ghcr.io/acme/app:not valid",
        "ghcr.io/acme/app@sha256:xyz",
    ],
)
def test_normalize_digest_image_reference_rejects_malformed_refs(ref: str) -> None:
    with pytest.raises(MalformedImageReferenceError):
        normalize_digest_image_reference(ref)


def test_signature_conformance_per_method() -> None:
    port_localns = {
        "ImageRef": ImageRef,
        "ImageDigestRef": ImageDigestRef,
        "LocalImageRef": LocalImageRef,
        "bool": bool,
    }

    for name in ("publish", "pull", "resolve_digest", "exists"):
        port_method = getattr(ImageRegistryProvider, name)
        impl_method = getattr(_FakeImageRegistryProvider, name)

        port_sig = inspect.signature(port_method)
        impl_sig = inspect.signature(impl_method)
        assert list(port_sig.parameters) == list(impl_sig.parameters)

        port_hints = typing.get_type_hints(port_method, localns=port_localns)
        impl_hints = typing.get_type_hints(impl_method)
        param_name = next(parameter for parameter in port_sig.parameters if parameter != "self")

        assert str(port_hints[param_name]) == str(impl_hints[param_name])
        assert str(port_hints["return"]) == str(impl_hints["return"])
