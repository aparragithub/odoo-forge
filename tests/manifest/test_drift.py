from odoo_forge.manifest.drift import DriftEntry, detect_drift
from odoo_forge.manifest.lockfile import Lockfile, ResolvedLayer, ResolvedRepo, compute_manifest_hash
from odoo_forge.manifest.schema import Manifest
from odoo_forge.manifest.state import MaterializedLayer, MaterializedRepo, MaterializedState


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
    materialized = MaterializedState(
        layers=[
            MaterializedLayer(
                name="localization",
                repos=[
                    MaterializedRepo(url="https://github.com/ingadhoc/odoo-partner.git", commit="abc123")
                ],
            )
        ]
    )

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
    entry = report.manifest_lock_drift[0]
    assert entry.kind == "manifest_lock_hash"
    assert entry.expected == compute_manifest_hash(manifest)
    assert entry.actual == "stale-hash-does-not-match"


def test_missing_lock_is_structured_entry() -> None:
    manifest = _manifest()

    report = detect_drift(manifest, None, None)

    assert report.is_clean is False
    assert len(report.manifest_lock_drift) == 1
    assert report.manifest_lock_drift[0].kind == "missing_lock"
    assert report.lock_state_drift == []


def _multi_repo_manifest() -> Manifest:
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
                        {"url": "https://github.com/ingadhoc/odoo-sale.git", "ref": "19.0"},
                    ],
                },
            ],
            "client": {"addons_path": "client/addons"},
        }
    )


def test_multi_repo_layer_detects_per_repo_drift() -> None:
    manifest = _multi_repo_manifest()
    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="localization",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0", commit="partner-locked"
                    ),
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-sale.git", ref="19.0", commit="sale-locked"
                    ),
                ],
            )
        ],
    )
    # partner matches the lock; sale has drifted on disk.
    materialized = MaterializedState(
        layers=[
            MaterializedLayer(
                name="localization",
                repos=[
                    MaterializedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git", commit="partner-locked"
                    ),
                    MaterializedRepo(
                        url="https://github.com/ingadhoc/odoo-sale.git", commit="sale-DRIFTED"
                    ),
                ],
            )
        ]
    )

    report = detect_drift(manifest, lock, materialized)

    assert report.manifest_lock_drift == []
    assert report.lock_state_drift == [
        DriftEntry(
            kind="commit_mismatch",
            layer="localization",
            repo="https://github.com/ingadhoc/odoo-sale.git",
            expected="sale-locked",
            actual="sale-DRIFTED",
        )
    ]


def test_lock_layer_not_materialized() -> None:
    manifest = _manifest()
    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="localization",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0", commit="abc123"
                    )
                ],
            )
        ],
    )
    materialized = MaterializedState(layers=[])

    report = detect_drift(manifest, lock, materialized)

    assert report.manifest_lock_drift == []
    assert report.lock_state_drift == [DriftEntry(kind="not_materialized", layer="localization")]


def test_lock_repo_not_materialized() -> None:
    manifest = _multi_repo_manifest()
    lock = Lockfile(
        generated_from=compute_manifest_hash(manifest),
        layers=[
            ResolvedLayer(
                name="localization",
                repos=[
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0", commit="partner-locked"
                    ),
                    ResolvedRepo(
                        url="https://github.com/ingadhoc/odoo-sale.git", ref="19.0", commit="sale-locked"
                    ),
                ],
            )
        ],
    )
    materialized = MaterializedState(
        layers=[
            MaterializedLayer(
                name="localization",
                repos=[
                    MaterializedRepo(
                        url="https://github.com/ingadhoc/odoo-partner.git", commit="partner-locked"
                    ),
                ],
            )
        ]
    )

    report = detect_drift(manifest, lock, materialized)

    assert report.lock_state_drift == [
        DriftEntry(
            kind="not_materialized",
            layer="localization",
            repo="https://github.com/ingadhoc/odoo-sale.git",
        )
    ]
