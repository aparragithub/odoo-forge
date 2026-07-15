import inspect
from pathlib import Path

import pytest
import yaml

from odoo_forge.manifest import composition
from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.errors import CompositionError
from odoo_forge.manifest.schema import CoreLayer, GitLayer, Manifest, PublishedLayer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _base_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
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


def test_community_rejects_layer_level_enterprise_published() -> None:
    # Layer-level `requires_edition: enterprise` (a PublishedLayer, no nested
    # repos) must fail under community — exercises the layer-level gating branch.
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
                {
                    "type": "published",
                    "name": "enterprise",
                    "source": "registry://example/odoo-ee",
                    "version": "19.0.1",
                    "requires_edition": "enterprise",
                },
            ],
        )
    )

    with pytest.raises(CompositionError, match="enterprise"):
        compose(manifest)


def test_override_targeting_git_layer_repo_is_accepted() -> None:
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
                    "repo": "https://github.com/ingadhoc/odoo-partner.git",
                    "fork": "https://github.com/acme/odoo-partner.git",
                    "ref": "custom",
                }
            ],
        )
    )

    chain = compose(manifest)

    assert len(chain) == 3


def test_override_requires_exact_declared_repository_url() -> None:
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
                    "repo": "odoo-partner",
                    "fork": "https://github.com/acme/odoo-partner.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="odoo-partner"):
        compose(manifest)


def test_duplicate_override_target_is_rejected() -> None:
    repo_url = "https://github.com/ingadhoc/odoo-partner.git"
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
                {
                    "type": "git",
                    "name": "localization",
                    "repos": [{"url": repo_url, "ref": "19.0"}],
                }
            ],
            overrides=[
                {
                    "layer": "localization",
                    "repo": repo_url,
                    "fork": "https://acme/one.git",
                    "ref": "one",
                },
                {
                    "layer": "localization",
                    "repo": repo_url,
                    "fork": "https://acme/two.git",
                    "ref": "two",
                },
            ],
        )
    )

    with pytest.raises(CompositionError, match="duplicate"):
        compose(manifest)


def test_override_targeting_published_layer_is_rejected() -> None:
    # A repo-level override is meaningless for a PublishedLayer (it has no repos),
    # so it must be rejected instead of silently passing.
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
            overrides=[
                {
                    "layer": "extra",
                    "repo": "whatever",
                    "fork": "https://github.com/acme/fork.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="extra"):
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
                    "repo": "https://github.com/ingadhoc/odoo-nonexistent.git",
                    "fork": "https://github.com/acme/fork.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="odoo-nonexistent"):
        compose(manifest)


def test_override_targeting_core_is_rejected() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            overrides=[
                {
                    "layer": "core",
                    "repo": "https://github.com/odoo/odoo.git",
                    "fork": "https://github.com/acme/odoo.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="core"):
        compose(manifest)


def test_compose_passes_core_through_unchanged() -> None:
    # compose() does NO ref resolution (there is none in this slice); it simply
    # places `manifest.core` first in the chain unchanged. This guards that
    # identity/passthrough, not any (nonexistent) resolution logic.
    manifest = Manifest.model_validate(_base_kwargs())

    chain = compose(manifest)

    assert chain[0] is manifest.core
    assert chain[0].ref is None


def test_compose_regression_core_ref_stays_none_and_helper_never_called() -> None:
    # Slice 2a introduces `resolve_default_ref` as a standalone, opt-in helper.
    # This regression guards that `compose()` stays byte-for-byte behaviorally
    # unchanged: it must never import or call it, and the composed core's `ref`
    # must remain `None` for an unresolved manifest.
    manifest = Manifest.model_validate(_base_kwargs())

    chain = compose(manifest)

    assert chain[0] is manifest.core
    assert chain[0].ref is None
    assert "resolve_default_ref" not in inspect.getsource(composition)


@pytest.mark.parametrize(
    ("fixture_name", "minimum_repos"),
    [("valid.project.yaml", 1), ("odoo-idp.project.yaml", 17)],
)
def test_tracked_manifest_fixture_composes_with_exact_override_url(
    fixture_name: str, minimum_repos: int
) -> None:
    raw = yaml.safe_load((FIXTURES_DIR / fixture_name).read_text())
    manifest = Manifest.model_validate(raw)

    chain = compose(manifest)

    assert isinstance(chain[0], CoreLayer)
    assert isinstance(chain[-1], type(manifest.client))
    localization = next(layer for layer in manifest.layers if isinstance(layer, GitLayer))
    assert len(localization.repos) >= minimum_repos
    assert manifest.overrides[0].repo == localization.repos[0].url


def test_additional_layer_named_core_is_rejected_even_with_a_matching_override() -> None:
    manifest = Manifest.model_validate(
        _base_kwargs(
            layers=[
                {
                    "type": "git",
                    "name": "core",
                    "repos": [{"url": "https://example.com/shadow.git", "ref": "main"}],
                }
            ],
            overrides=[
                {
                    "layer": "core",
                    "repo": "https://example.com/shadow.git",
                    "fork": "https://example.com/fork.git",
                    "ref": "custom",
                }
            ],
        )
    )

    with pytest.raises(CompositionError, match="reserved"):
        compose(manifest)
