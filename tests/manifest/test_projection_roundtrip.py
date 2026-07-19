"""End-to-end round-trip: plan_projection -> project_workspace -> scan ->
materialize_state -> detect_drift, using a fake in-memory `WorkspaceProvider`
(no real git/network). Proves the pipeline reports no false drift on a
matching workspace, and correct `not_materialized`/`commit_mismatch` drift
on divergence.
"""

from pathlib import Path

from odoo_forge.manifest.drift import detect_drift
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.projection import (
    CONTAINER_MOUNT_BASE,
    ScannedRepo,
    build_mount_roots,
    materialize_state,
    plan_projection,
    project_workspace,
)
from odoo_forge.manifest.schema import Manifest


class _InMemoryWorkspaceProvider:
    """Fake `WorkspaceProvider`: `checkout` records a materialized repo at the
    target path instead of touching a real filesystem; `scan` replays exactly
    what was checked out. No I/O anywhere in this double."""

    def __init__(self) -> None:
        self._materialized: dict[Path, tuple[str, str]] = {}

    def checkout(self, url: str, commit: str, dest: Path) -> None:
        self._materialized[dest] = (url, commit)

    def scan(self, roots: object) -> list[ScannedRepo]:
        return [
            ScannedRepo(path=path, url=url, commit=commit)
            for path, (url, commit) in self._materialized.items()
        ]

    def promote(self, source: Path, dest: Path, branch: str) -> None:
        raise NotImplementedError


def _manifest() -> Manifest:
    return Manifest.model_validate(
        {
            "name": "odoo-idp",
            "odoo_version": "19.0",
            "edition": "community",
            "core": {"type": "core", "url": "https://github.com/odoo/odoo.git", "ref": "19.0"},
            "layers": [
                {
                    "type": "git",
                    "name": "custom-x",
                    "repos": [
                        {"url": "https://github.com/ingadhoc/odoo-partner.git", "ref": "19.0"},
                    ],
                },
            ],
            "client": {"addons_path": "client/addons"},
        }
    )


def _lock(manifest: Manifest) -> Lockfile:
    return Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="core",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/odoo/odoo.git", ref="19.0", commit="core-sha"
                    )
                ],
            ),
            ResolvedLayer(
                name="custom-x",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git",
                        ref="19.0",
                        commit="partner-sha",
                    )
                ],
            ),
        ],
    )


def test_round_trip_no_false_drift_on_matching_workspace() -> None:
    manifest = _manifest()
    lock = _lock(manifest)
    roots = build_mount_roots(CONTAINER_MOUNT_BASE, manifest)
    provider = _InMemoryWorkspaceProvider()

    plan = plan_projection(manifest, lock, roots)
    project_workspace(plan, provider)

    scanned = provider.scan(list(roots.values()))
    materialized = materialize_state(scanned, roots)
    report = detect_drift(manifest, lock, materialized)

    assert report.is_clean


def test_round_trip_reports_not_materialized_when_never_projected() -> None:
    manifest = _manifest()
    lock = _lock(manifest)
    roots = build_mount_roots(CONTAINER_MOUNT_BASE, manifest)
    provider = _InMemoryWorkspaceProvider()

    # No project_workspace call — nothing was ever checked out.
    scanned = provider.scan(list(roots.values()))
    materialized = materialize_state(scanned, roots)
    report = detect_drift(manifest, lock, materialized)

    assert not report.is_clean
    kinds_and_layers = {(entry.kind, entry.layer) for entry in report.lock_state_drift}
    assert ("not_materialized", "core") in kinds_and_layers
    assert ("not_materialized", "custom-x") in kinds_and_layers


def test_round_trip_reports_commit_mismatch_on_stale_checkout() -> None:
    manifest = _manifest()
    lock = _lock(manifest)
    roots = build_mount_roots(CONTAINER_MOUNT_BASE, manifest)
    provider = _InMemoryWorkspaceProvider()

    plan = plan_projection(manifest, lock, roots)
    project_workspace(plan, provider)

    # Simulate drift: the on-disk checkout is now at a stale commit that no
    # longer matches the lock (e.g. an out-of-band `git checkout` elsewhere).
    stale_path = next(iter(provider._materialized))
    url, _stale_commit = provider._materialized[stale_path]
    provider._materialized[stale_path] = (url, "stale-commit")

    scanned = provider.scan(list(roots.values()))
    materialized = materialize_state(scanned, roots)
    report = detect_drift(manifest, lock, materialized)

    assert not report.is_clean
    mismatch = next(entry for entry in report.lock_state_drift if entry.kind == "commit_mismatch")
    assert mismatch.actual == "stale-commit"
