from odoo_forge.manifest.drift import detect_drift
from odoo_forge.manifest.lockfile import Lockfile, ResolvedLayer, ResolvedRepo, compute_manifest_hash
from odoo_forge.manifest.schema import Manifest
from odoo_forge.manifest.state import MaterializedLayer, MaterializedState


def _manifest() -> Manifest:
    return Manifest.model_validate(
        {
            "name": "odoo-idp",
            "odoo_version": "19.0",
            "edition": "community",
            "layers": [
                {
                    "type": "git",
                    "name": "localization",
                    "repos": [
                        {"url": "https://github.com/ingadhoc/odoo-partner.git", "ref": "19.0"},
                    ],
                },
            ],
            "client": {"addons_path": "client/addons"},
        }
    )


def test_clean_state_is_clean() -> None:
    manifest = _manifest()
    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="localization",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git",
                        ref="19.0",
                        commit="abc123",
                    )
                ],
            )
        ],
    )
    materialized = MaterializedState(layers=[MaterializedLayer(name="localization", commit="abc123")])

    report = detect_drift(manifest, lock, materialized)

    assert report.is_clean is True
    assert report.manifest_lock_drift == []
    assert report.lock_state_drift == []


def test_manifest_changed_lock_stale() -> None:
    manifest = _manifest()
    stale_lock = Lockfile(generated_from="stale-hash-does-not-match", layers=[])

    report = detect_drift(manifest, stale_lock, None)

    assert report.is_clean is False
    assert len(report.manifest_lock_drift) == 1


def test_lock_state_drift_and_none_inputs() -> None:
    manifest = _manifest()

    report_no_lock = detect_drift(manifest, None, None)
    assert report_no_lock.is_clean is False
    assert len(report_no_lock.manifest_lock_drift) == 1
    assert report_no_lock.lock_state_drift == []

    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="localization",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git",
                        ref="19.0",
                        commit="abc123",
                    )
                ],
            )
        ],
    )
    drifted_state = MaterializedState(layers=[MaterializedLayer(name="localization", commit="different-commit")])

    report_drifted = detect_drift(manifest, lock, drifted_state)
    assert report_drifted.is_clean is False
    assert report_drifted.manifest_lock_drift == []
    assert len(report_drifted.lock_state_drift) == 1
