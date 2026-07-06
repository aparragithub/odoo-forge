"""Domain error types for manifest parsing and composition."""


class ManifestError(Exception):
    """Raised for manifest-level domain errors."""


class CompositionError(ManifestError):
    """Raised when `compose()` cannot produce a valid layer chain."""


__all__ = ["ManifestError", "CompositionError"]
