from odoo_forge.manifest.errors import (
    AuthenticationError,
    ManifestError,
    NetworkError,
    RefNotFoundError,
    ResolutionError,
)


def test_resolution_error_family() -> None:
    assert issubclass(RefNotFoundError, ResolutionError)
    assert issubclass(AuthenticationError, ResolutionError)
    assert issubclass(NetworkError, ResolutionError)
    assert not issubclass(ResolutionError, ManifestError)
