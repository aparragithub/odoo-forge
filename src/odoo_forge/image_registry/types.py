"""Lightweight value types for image-registry contracts."""

from typing import NewType

ImageRef = NewType("ImageRef", str)
ImageDigestRef = NewType("ImageDigestRef", str)
LocalImageRef = NewType("LocalImageRef", str)


__all__ = ["ImageRef", "ImageDigestRef", "LocalImageRef"]
