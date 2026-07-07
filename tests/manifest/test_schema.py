from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError, TypeAdapter

from odoo_forge.manifest.schema import CoreLayer, GitLayer, GitRepo, Layer, Manifest, PublishedLayer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _base_manifest_kwargs() -> dict:
    return {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": {"addons_path": "client/addons"},
    }


def test_manifest_requires_core_field() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    assert isinstance(manifest.core, CoreLayer)


def test_core_default_url_and_ref_none() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    assert manifest.core.url == "https://github.com/odoo/odoo.git"
    assert manifest.core.ref is None


def test_requires_edition_on_repo_and_layer() -> None:
    repo = GitRepo(
        url="https://github.com/ingadhoc/odoo-argentina-ee.git",
        ref="19.0",
        requires_edition="enterprise",
    )
    git_layer = GitLayer(type="git", name="localization", repos=[repo], requires_edition="enterprise")
    published_layer = PublishedLayer(
        type="published",
        name="enterprise",
        source="registry://example/odoo-ee",
        version="19.0.1",
        requires_edition="enterprise",
    )

    assert repo.requires_edition == "enterprise"
    assert git_layer.requires_edition == "enterprise"
    assert published_layer.requires_edition == "enterprise"


def test_discriminated_layer_single_error() -> None:
    layer_adapter = TypeAdapter(Layer)
    malformed = {"type": "git", "name": "localization"}  # missing required `repos`

    with pytest.raises(ValidationError) as exc_info:
        layer_adapter.validate_python(malformed)

    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"][0] == "git"


def test_client_and_override_and_manifest_parse() -> None:
    manifest_dict = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "enterprise",
        "core": {"type": "core", "url": "https://github.com/odoo/odoo.git", "ref": "19.0"},
        "layers": [
            {
                "type": "published",
                "name": "enterprise",
                "source": "registry://example/odoo-ee",
                "version": "19.0.1",
                "requires_edition": "enterprise",
            },
            {
                "type": "git",
                "name": "localization",
                "repos": [
                    {
                        "url": "https://github.com/ingadhoc/odoo-argentina-ee.git",
                        "ref": "19.0",
                        "requires_edition": "enterprise",
                    }
                ],
            },
        ],
        "client": {"addons_path": "client/addons", "python_requirements": "client/requirements.txt"},
        "overrides": [
            {"layer": "localization", "repo": "odoo-argentina-ee", "fork": "https://github.com/acme/fork.git", "ref": "custom"},
        ],
    }

    manifest = Manifest.model_validate(manifest_dict)

    assert manifest.name == "odoo-idp"
    assert manifest.client.addons_path == Path("client/addons")
    assert len(manifest.layers) == 2
    assert isinstance(manifest.layers[0], PublishedLayer)
    assert isinstance(manifest.layers[1], GitLayer)
    assert manifest.overrides[0].repo == "odoo-argentina-ee"


def test_client_has_type_discriminator_default() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    # Client carries a `type` tag so the whole composed chain
    # (core -> layers -> client) is uniformly discriminable.
    assert manifest.client.type == "client"


def test_valid_fixture_parses_into_manifest() -> None:
    raw = yaml.safe_load((FIXTURES_DIR / "valid.project.yaml").read_text())

    manifest = Manifest.model_validate(raw)

    assert manifest.edition == "enterprise"
    assert isinstance(manifest.layers[1], GitLayer)
    assert manifest.layers[1].repos[0].requires_edition == "enterprise"


def test_malformed_fixture_yields_single_scoped_error() -> None:
    raw = yaml.safe_load((FIXTURES_DIR / "malformed.project.yaml").read_text())

    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(raw)

    errors = exc_info.value.errors()
    layer_errors = [e for e in errors if e["loc"][0] == "layers"]
    assert len(layer_errors) == 1
    assert layer_errors[0]["loc"][2] == "git"
