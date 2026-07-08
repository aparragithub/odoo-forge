from pathlib import Path

from odoo_forge.manifest.projection import ScannedRepo
from odoo_forge.manifest.state import MaterializedState
from odoo_forge.ports.workspace_provider import WorkspaceProvider


class _FakeWorkspaceProvider:
    """Structural stand-in — not a real adapter, just satisfies the shape."""

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        pass

    def scan(self, roots: list[Path]) -> list[ScannedRepo]:
        return [ScannedRepo(path=roots[0], url="https://example.com/repo.git", commit="sha")]

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        pass


def test_conforming_class_satisfies_workspace_provider_protocol() -> None:
    provider = _FakeWorkspaceProvider()

    assert isinstance(provider, WorkspaceProvider)

    scanned = provider.scan([Path("/mnt/community")])
    assert scanned[0].url == "https://example.com/repo.git"


def test_non_conforming_class_does_not_satisfy_protocol() -> None:
    class _NotAProvider:
        pass

    assert not isinstance(_NotAProvider(), WorkspaceProvider)


def test_materialized_state_stays_provider_free() -> None:
    # Sanity check: `MaterializedState` (consumed by `detect_drift`) is a
    # plain in-memory model, never produced directly by the Protocol here —
    # `scan` returns raw `ScannedRepo` values; mapping to `MaterializedState`
    # is a separate pure use-case (later slice).
    assert MaterializedState().layers == []
