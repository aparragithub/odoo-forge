from pathlib import Path

import pytest
import yaml

from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.errors import CompositionError
from odoo_forge.manifest.schema import CoreLayer, GitLayer, GitRepo, Manifest, PublishedLayer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _base_kwargs(**overrides) -> dict:
    kwargs = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": {"addons_path": "client/addons"},
    }
    kwargs.update(overrides)
    return kwargs


def test_onion_order_core_first_client_last() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
                {
                    "type": "published",
                    "name": "extra",
                    "source": "registry://example/extra",
                    "version": "1.0.0",
                },
            ],
        )
    )

    chain = compose(manifest)

    assert isinstance(chain[0], CoreLayer)
    assert isinstance(chain[1], PublishedLayer)
    assert chain[1].name == "extra"
    assert chain[-1] == manifest.client


def test_composed_chain_is_uniformly_type_tagged() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
                {
                    "type": "published",
                    "name": "extra",
                    "source": "registry://example/extra",
                    "version": "1.0.0",
                },
            ],
        )
    )

    chain = compose(manifest)

    # Every member of the chain exposes a `type` discriminator.
    assert [member.type for member in chain] == ["core", "published", "client"]


def test_compose_empty_layers_chain_is_core_then_client() -> None:
    manifest = Manifest.model_validate(_base_kwargs(layers=[]))

    chain = compose(manifest)

    assert len(chain) == 2
    assert isinstance(chain[0], CoreLayer)
    assert chain[1] is manifest.client


def test_community_rejects_nested_enterprise_repo() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
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
        )
    )

    with pytest.raises(CompositionError, match="odoo-argentina-ee"):
        compose(manifest)


def test_enterprise_manifest_accepts_same_repo() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            edition="enterprise",
            layers=[
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
        )
    )

    chain = compose(manifest)

    assert len(chain) == 3


def test_override_missing_layer_raises_no_io() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            overrides=[
                {
                    "layer": "does-not-exist",
                    "repo": "some-repo",
                    "fork": "https://github.com/acme/fork.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="does-not-exist"):
        compose(manifest)


def test_override_missing_repo_in_existing_layer_raises() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
                {
                    "type": "git",
                    "name": "localization",
                    "repos": [
                        {"url": "https://github.com/ingadhoc/odoo-partner.git", "ref": "19.0"},
                    ],
                },
            ],
            overrides=[
                {
                    "layer": "localization",
                    "repo": "odoo-nonexistent",
                    "fork": "https://github.com/acme/fork.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="odoo-nonexistent"):
        compose(manifest)


def test_compose_preserves_unresolved_core_ref() -> None:
    manifest = Manifest.model_validate(_base_kwargs())

    assert manifest.core.ref is None

    chain = compose(manifest)

    assert chain[0].ref is None


def test_odoo_idp_fire_test_composes_cleanly() -> None:
    raw = yaml.safe_load((FIXTURES_DIR / "odoo-idp.project.yaml").read_text())
    manifest = Manifest.model_validate(raw)

    chain = compose(manifest)

    assert isinstance(chain[0], CoreLayer)
    assert isinstance(chain[-1], type(manifest.client))
    localization = next(layer for layer in manifest.layers if isinstance(layer, GitLayer))
    assert len(localization.repos) >= 17
