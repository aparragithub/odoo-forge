from odoo_forge.manifest.errors import (
    AlreadyUnlockedError,
    AuthenticationError,
    CheckoutError,
    ManifestError,
    NetworkError,
    ProjectionError,
    PromotionError,
    RefNotFoundError,
    ResolutionError,
    ScanError,
    WorkspaceError,
)


def test_resolution_error_family() -> None:
    assert issubclass(RefNotFoundError, ResolutionError)
    assert issubclass(AuthenticationError, ResolutionError)
    assert issubclass(NetworkError, ResolutionError)
    assert not issubclass(ResolutionError, ManifestError)


def test_workspace_error_family() -> None:
    assert issubclass(WorkspaceError, ManifestError)
    assert issubclass(ProjectionError, WorkspaceError)
    assert issubclass(CheckoutError, WorkspaceError)
    assert issubclass(ScanError, WorkspaceError)
    assert issubclass(PromotionError, WorkspaceError)
    assert issubclass(AlreadyUnlockedError, WorkspaceError)
