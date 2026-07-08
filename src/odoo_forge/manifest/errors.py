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


class ResolutionError(Exception):
    """Base class for ref-resolution errors, separate from `ManifestError`.

    Raised by concrete `SourceProvider` adapters (e.g. the git adapter in
    `odoo_forge_git`) when a `url`/`ref` pair cannot be resolved to a commit
    SHA. Kept as its own family so callers can catch resolution failures
    distinctly from manifest parsing/composition failures.
    """


class RefNotFoundError(ResolutionError):
    """Raised when a ref does not exist on the given remote."""

    def __init__(self, url: str, ref: str) -> None:
        self.url = url
        self.ref = ref
        super().__init__(f"ref '{ref}' not found on remote '{url}'")


class AuthenticationError(ResolutionError):
    """Raised when the remote rejects ambient credentials."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"authentication failed for remote '{url}'")


class NetworkError(ResolutionError):
    """Raised when the remote cannot be reached."""

    def __init__(self, url: str, detail: str) -> None:
        self.url = url
        self.detail = detail
        super().__init__(f"cannot reach remote '{url}': {detail}")


class WorkspaceError(ManifestError):
    """Base class for workspace projection/materialization errors.

    Raised by the pure planning use-cases in `manifest/projection.py` and by
    concrete `WorkspaceProvider` adapters (e.g. the git adapter in
    `odoo_forge_workspace`) when a filesystem checkout/scan/promote step
    cannot complete. Kept as its own family so callers can catch workspace
    failures distinctly from manifest parsing/composition/resolution
    failures.
    """


class ProjectionError(WorkspaceError):
    """Raised when `plan_projection` cannot resolve a locked layer against the manifest."""


class CheckoutError(WorkspaceError):
    """Raised when a `WorkspaceProvider` cannot check out a repo cleanly."""


class ScanError(WorkspaceError):
    """Raised when a `WorkspaceProvider` cannot read a materialized repo's state."""


class PromotionError(WorkspaceError):
    """Raised when a `WorkspaceProvider` cannot promote a repo to writable."""


class AlreadyUnlockedError(WorkspaceError):
    """Raised when `unlock` targets a repo that is already writable."""


__all__ = [
    "ManifestError",
    "ManifestInputError",
    "CompositionError",
    "LockfileError",
    "ResolutionError",
    "RefNotFoundError",
    "AuthenticationError",
    "NetworkError",
    "WorkspaceError",
    "ProjectionError",
    "CheckoutError",
    "ScanError",
    "PromotionError",
    "AlreadyUnlockedError",
]
