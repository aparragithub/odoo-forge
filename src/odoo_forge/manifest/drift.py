"""Pure three-input drift detection: manifest, lock, materialized state.

`detect_drift` never reads disk; it consumes already-loaded in-memory
models and reports manifest<->lock and lock<->state drift independently.
"""

from pydantic import BaseModel

from odoo_forge.manifest.lockfile import Lockfile, compute_manifest_hash
from odoo_forge.manifest.schema import Manifest
from odoo_forge.manifest.state import MaterializedState


class DriftReport(BaseModel):
    manifest_lock_drift: list[str] = []
    lock_state_drift: list[str] = []

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


def _manifest_lock_drift(manifest: Manifest, lock: Lockfile | None) -> list[str]:
    if lock is None:
        return ["no lockfile present — manifest has never been locked"]

    current_hash = compute_manifest_hash(manifest)
    if lock.generated_from != current_hash:
        return [f"manifest hash '{current_hash}' does not match lock's '{lock.generated_from}'"]

    return []


def _lock_state_drift(lock: Lockfile | None, materialized: MaterializedState | None) -> list[str]:
    if lock is None or materialized is None:
        return []

    materialized_by_name = {layer.name: layer for layer in materialized.layers}
    drift: list[str] = []

    for lock_layer in lock.layers:
        materialized_layer = materialized_by_name.get(lock_layer.name)
        if materialized_layer is None:
            drift.append(f"layer '{lock_layer.name}' is not materialized")
            continue

        for repo in lock_layer.repos:
            if materialized_layer.commit != repo.commit:
                drift.append(
                    f"layer '{lock_layer.name}' materialized at commit "
                    f"'{materialized_layer.commit}' but lock declares '{repo.commit}'"
                )

    return drift


__all__ = ["DriftReport", "detect_drift"]
