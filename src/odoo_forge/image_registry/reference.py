"""Pure GHCR-only image reference parsing helpers."""

import re

from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    UnsupportedRegistryError,
)

_SUPPORTED_REGISTRY = "ghcr.io"
_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_NAME_PART_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def normalize_image_reference(ref: str, *, require_digest: bool) -> str:
    registry, remainder = _split_registry(ref)
    if registry != _SUPPORTED_REGISTRY:
        raise UnsupportedRegistryError(registry, supported=_SUPPORTED_REGISTRY)

    if "@" in remainder:
        name, digest = remainder.split("@", 1)
        _validate_name(name, ref)
        if not _DIGEST_RE.fullmatch(digest):
            raise MalformedImageReferenceError(ref, "digest must be sha256:<64 lowercase hex>")
        return f"{registry}/{name}@{digest}"

    if require_digest:
        raise MalformedImageReferenceError(ref, "digest reference required")

    if ":" not in remainder:
        raise MalformedImageReferenceError(ref, "tag reference must include :<tag>")

    name, tag = remainder.rsplit(":", 1)
    _validate_name(name, ref)
    if not _TAG_RE.fullmatch(tag):
        raise MalformedImageReferenceError(ref, "tag contains unsupported characters")
    return f"{registry}/{name}:{tag}"


def _split_registry(ref: str) -> tuple[str, str]:
    if not ref or any(char.isspace() for char in ref):
        raise MalformedImageReferenceError(ref, "reference must not be empty or contain whitespace")
    if "/" not in ref:
        raise MalformedImageReferenceError(ref, "reference must include a registry and image path")
    registry, remainder = ref.split("/", 1)
    if not remainder:
        raise MalformedImageReferenceError(ref, "image path is missing")
    return registry, remainder


def _validate_name(name: str, ref: str) -> None:
    parts = [part for part in name.split("/") if part]
    if len(parts) < 2:
        raise MalformedImageReferenceError(ref, "image path must include owner and image name")
    if len(parts) != len(name.split("/")):
        raise MalformedImageReferenceError(ref, "image path contains empty segments")
    for part in parts:
        if not _NAME_PART_RE.fullmatch(part):
            raise MalformedImageReferenceError(ref, "image path contains unsupported characters")


__all__ = ["normalize_image_reference"]
