"""Pure three-input drift detection: manifest, lock, materialized state.

`detect_drift` never reads disk; it consumes already-loaded in-memory
models and reports manifest<->lock and lock<->state drift independently.

Drift is reported as structured `DriftEntry` values (not pre-formatted
sentences). Human-readable rendering lives at the presentation boundary
(`odoo_forge_cli`), so the domain stays free of display concerns.
"""

from typing import Literal

from pydantic import BaseModel

from odoo_forge.manifest.lockfile import Lockfile, compute_manifest_hash
from odoo_forge.manifest.schema import Manifest
from odoo_forge.manifest.state import MaterializedState

# Drift kinds:
#   manifest_lock_hash -> manifest content no longer matches the lock's hash
#   missing_lock       -> no lockfile exists yet for this manifest
#   not_materialized   -> a locked layer/repo is absent from the workspace
#   commit_mismatch    -> a repo is materialized at a different commit than locked
DriftKind = Literal["manifest_lock_hash", "missing_lock", "not_materialized", "commit_mismatch"]


class DriftEntry(BaseModel):
    kind: DriftKind
    layer: str | None = None
    repo: str | None = None
    # For manifest_lock_hash: expected = current manifest hash, actual = lock's hash.
    # For commit_mismatch: expected = commit the lock declares, actual = materialized commit.
    expected: str | None = None
    actual: str | None = None


class DriftReport(BaseModel):
    manifest_lock_drift: list[DriftEntry] = []
    lock_state_drift: list[DriftEntry] = []

    @property
    def is_clean(self) -> bool:
        return not self.manifest_lock_drift and not self.lock_state_drift


def detect_drift(
    manifest: Manifest,
    lock: Lockfile | None,
    materialized: MaterializedState | None,
) -> DriftReport:
    manifest_lock_drift = _manifest_lock_drift(manifest, lock)
    lock_state_drift = _lock_state_drift(lock, materialized)

    return DriftReport(manifest_lock_drift=manifest_lock_drift, lock_state_drift=lock_state_drift)


def _manifest_lock_drift(manifest: Manifest, lock: Lockfile | None) -> list[DriftEntry]:
    if lock is None:
        return [DriftEntry(kind="missing_lock")]

    current_hash = compute_manifest_hash(manifest)
    if lock.generated_from != current_hash:
        return [
            DriftEntry(
                kind="manifest_lock_hash",
                expected=current_hash,
                actual=lock.generated_from,
            )
        ]

    return []


def _lock_state_drift(
    lock: Lockfile | None, materialized: MaterializedState | None
) -> list[DriftEntry]:
    if lock is None or materialized is None:
        return []

    materialized_by_name = {layer.name: layer for layer in materialized.layers}
    drift: list[DriftEntry] = []

    for lock_layer in lock.layers:
        materialized_layer = materialized_by_name.get(lock_layer.name)
        if materialized_layer is None:
            drift.append(DriftEntry(kind="not_materialized", layer=lock_layer.name))
            continue

        materialized_by_url = {repo.url: repo for repo in materialized_layer.repos}
        for repo in lock_layer.repos:
            materialized_repo = materialized_by_url.get(repo.url)
            if materialized_repo is None:
                drift.append(
                    DriftEntry(kind="not_materialized", layer=lock_layer.name, repo=repo.url)
                )
                continue
            if materialized_repo.commit != repo.commit:
                drift.append(
                    DriftEntry(
                        kind="commit_mismatch",
                        layer=lock_layer.name,
                        repo=repo.url,
                        expected=repo.commit,
                        actual=materialized_repo.commit,
                    )
                )

    return drift


__all__ = ["DriftReport", "DriftEntry", "DriftKind", "detect_drift"]
