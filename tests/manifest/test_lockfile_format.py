import json

from odoo_forge.manifest.lockfile import (
    LOCKFILE_SCHEMA_VERSION,
    Lockfile,
    ResolvedLayer,
    ResolvedRepo,
)


def _lockfile() -> Lockfile:
    return Lockfile(
        generated_from="abc123",
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


def test_serialize_includes_schema_version_field() -> None:
    lock = _lockfile()

    raw = lock.to_canonical_json()
    data = json.loads(raw)

    assert data["schema_version"] == LOCKFILE_SCHEMA_VERSION


def test_to_canonical_json_sorts_keys_preserves_layer_order() -> None:
    lock = Lockfile(
        generated_from="abc123",
        layers=[
            ResolvedLayer(name="first", repos=[]),
            ResolvedLayer(name="second", repos=[]),
        ],
    )

    raw = lock.to_canonical_json()

    # Top-level dict keys must be sorted alphabetically.
    top_level_keys = list(json.loads(raw).keys())
    assert top_level_keys == sorted(top_level_keys)

    # List order (semantically meaningful) must be preserved.
    data = json.loads(raw)
    assert [layer["name"] for layer in data["layers"]] == ["first", "second"]


def test_round_trip_serialize_deserialize_serialize_byte_identical() -> None:
    lock = _lockfile()

    first = lock.to_canonical_json()
    restored = Lockfile.from_json(first)
    second = restored.to_canonical_json()

    assert first == second


def test_legacy_lock_without_schema_version_defaults_to_one_and_reserializes_explicit() -> None:
    legacy_raw = json.dumps(
        {
            "generated_from": "abc123",
            "layers": [],
        }
    )

    restored = Lockfile.from_json(legacy_raw)

    assert restored.schema_version == 1

    reserialized = json.loads(restored.to_canonical_json())
    assert reserialized["schema_version"] == 1
