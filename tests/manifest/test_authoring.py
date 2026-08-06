from pathlib import Path

import pytest
import yaml

from odoo_forge.manifest.authoring import serialize_manifest, validate_draft
from odoo_forge.manifest.schema import Manifest


def _complete_draft() -> dict[str, object]:
    return {
        "name": "café-project",
        "odoo_version": "19.0",
        "edition": "enterprise",
        "core": {"type": "core", "url": "https://example.test/odoo.git", "ref": "19.0"},
        "enterprise": {"url": "https://example.test/enterprise.git", "ref": "19.0"},
        "layers": [
            {
                "type": "published",
                "name": "ee-addons",
                "source": "registry://example/ee",
                "version": "19.0.1",
                "category": "enterprise-addons",
                "requires_enterprise": True,
            },
            {
                "type": "git",
                "name": "localization",
                "repos": [
                    {"url": "https://example.test/latam.git", "ref": "19.0"},
                    {"url": "https://example.test/extra.git", "ref": "stable"},
                ],
                "category": "localization",
            },
        ],
        "client": {
            "addons_path": "client/addons",
            "python_requirements": "client/requirements.txt",
        },
        "overrides": [
            {
                "layer": "localization",
                "repo": "latam",
                "fork": "https://example.test/fork.git",
                "ref": "feature",
            }
        ],
        "workspace": {"checkout_timeout_seconds": 300},
        "backend": {"odoo": {"http_port": 18069, "bind_host": "127.0.0.1"}},
        "mount_priority": ["custom/localization", "enterprise"],
    }


def test_validate_draft_accepts_complete_manifest_surface() -> None:
    draft = _complete_draft()

    result = validate_draft(draft)

    assert result.manifest == Manifest.model_validate(draft)
    assert result.issues == ()


@pytest.mark.parametrize(
    ("draft", "path"),
    [
        (
            {
                "name": "demo",
                "odoo_version": "19.0",
                "edition": "community",
                "client": {},
                "layers": [{"type": "git", "name": "x"}],
            },
            "layers[0].git.repos",
        ),
        (
            {
                "name": "demo",
                "odoo_version": "19.0",
                "edition": "community",
                "client": {},
                "layers": [{"type": "published", "name": "x", "source": "registry://x"}],
            },
            "layers[0].published.version",
        ),
    ],
)
def test_validate_draft_reports_ordered_field_paths(draft: dict[str, object], path: str) -> None:
    result = validate_draft(draft)

    assert result.manifest is None
    assert [issue.path for issue in result.issues] == [path, "client.addons_path"]
    assert all(issue.message for issue in result.issues)


def test_serialize_manifest_is_canonical_and_round_trips_paths_and_unicode() -> None:
    result = validate_draft(_complete_draft())
    assert result.manifest is not None

    serialized = serialize_manifest(result.manifest)
    reloaded = Manifest.model_validate(yaml.safe_load(serialized))

    assert serialized.endswith("\n")
    assert not serialized.endswith("\n\n")
    assert "café-project" in serialized
    assert "addons_path: client/addons" in serialized
    assert reloaded == result.manifest


def test_equivalent_manifests_have_identical_yaml_bytes() -> None:
    first = Manifest.model_validate(_complete_draft())
    second = Manifest.model_validate(
        {
            "mount_priority": ["custom/localization", "enterprise"],
            "backend": {"odoo": {"bind_host": "127.0.0.1", "http_port": 18069}},
            **{
                key: value
                for key, value in _complete_draft().items()
                if key not in {"backend", "mount_priority"}
            },
        }
    )

    assert first == second
    assert serialize_manifest(first) == serialize_manifest(second)


def test_serialize_manifest_omits_unset_and_default_values() -> None:
    manifest = Manifest.model_validate(
        {
            "name": "minimal",
            "odoo_version": "19.0",
            "edition": "community",
            "client": {"addons_path": Path("client/addons")},
        }
    )

    document = yaml.safe_load(serialize_manifest(manifest))

    assert document == {
        "name": "minimal",
        "odoo_version": "19.0",
        "edition": "community",
        "client": {"addons_path": "client/addons"},
    }
