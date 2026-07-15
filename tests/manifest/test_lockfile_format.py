import json

import pytest

from odoo_forge.manifest.lockfile import (
    LOCKFILE_SCHEMA_VERSION,
    Lockfile,
    ResolvedGitLayer,
    ResolvedPublishedLayer,
    ResolvedRepo,
)


def _lockfile() -> Lockfile:
    return Lockfile(
        generated_from="abc123",
        git_layers=[
            ResolvedGitLayer(
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
        git_layers=[
            ResolvedGitLayer(name="first", repos=[]),
            ResolvedGitLayer(name="second", repos=[]),
        ],
    )

    raw = lock.to_canonical_json()

    # Top-level dict keys must be sorted alphabetically.
    top_level_keys = list(json.loads(raw).keys())
    assert top_level_keys == sorted(top_level_keys)

    # List order (semantically meaningful) must be preserved.
    data = json.loads(raw)
    assert [layer["name"] for layer in data["git_layers"]] == ["first", "second"]


def test_canonical_json_is_stable_for_equal_v2_lockfiles() -> None:
    first = Lockfile(
        generated_from="abc123",
        git_layers=[ResolvedGitLayer(name="localization", repos=[])],
        published_layers=[
            ResolvedPublishedLayer(
                name="oca",
                source="registry://oca",
                version="19.0.1",
                digest="sha256:abc123",
            )
        ],
    )
    second = Lockfile.model_validate(
        {
            "published_layers": first.published_layers,
            "schema_version": LOCKFILE_SCHEMA_VERSION,
            "git_layers": first.git_layers,
            "generated_from": "abc123",
        }
    )

    assert first.to_canonical_json() == second.to_canonical_json()


def test_v1_serialization_rejects_published_layers() -> None:
    lock = Lockfile(
        schema_version=1,
        generated_from="abc123",
        published_layers=[
            ResolvedPublishedLayer(
                name="oca",
                source="registry://oca",
                version="19.0.1",
                digest="sha256:abc123",
            )
        ],
    )

    with pytest.raises(ValueError, match="schema version 1 cannot contain published layers"):
        lock.to_canonical_json()


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
    assert restored.git_layers == []
    assert restored.published_layers == []

    reserialized = json.loads(restored.to_canonical_json())
    assert reserialized["schema_version"] == 1
    assert reserialized["layers"] == []
    assert "published_layers" not in reserialized


def test_v2_round_trip_preserves_git_and_published_layers() -> None:
    lock = Lockfile(
        generated_from="abc123",
        git_layers=[
            ResolvedGitLayer(
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
        published_layers=[
            ResolvedPublishedLayer(
                name="oca",
                source="registry://oca",
                version="19.0.1",
                digest="sha256:abc123",
            )
        ],
    )

    restored = Lockfile.from_json(lock.to_canonical_json())

    assert restored == lock
    assert restored.to_canonical_json() == lock.to_canonical_json()


@pytest.mark.parametrize("schema_version", [0, 3])
def test_unknown_schema_version_is_rejected(schema_version: int) -> None:
    raw = json.dumps(
        {
            "schema_version": schema_version,
            "generated_from": "abc123",
            "git_layers": [],
            "published_layers": [],
        }
    )

    with pytest.raises(ValueError, match=f"unsupported lockfile schema version: {schema_version}"):
        Lockfile.from_json(raw)
