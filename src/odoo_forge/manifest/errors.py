"""Domain error types for manifest parsing and composition.

These stay pure: they carry a message only and perform no I/O. The CLI
translates stdlib failures (OSError, YAMLError, JSONDecodeError,
ValidationError) into these typed errors so it can catch a single domain
error family at one boundary instead of scattering stdlib handling.
"""


class ManifestError(Exception):
    """Base class for manifest-level domain errors."""


class ManifestInputError(ManifestError):
    """Raised when the manifest cannot be read or is not parseable input.

    Covers missing/unreadable files and malformed YAML syntax — distinct from
    a structurally-invalid-but-parseable manifest, which surfaces as a
    pydantic ``ValidationError``.
    """


class CompositionError(ManifestError):
    """Raised when `compose()` cannot produce a valid layer chain."""


class LockfileError(ManifestError):
    """Raised when a `project.lock` cannot be read, decoded, or validated."""


__all__ = ["ManifestError", "ManifestInputError", "CompositionError", "LockfileError"]
