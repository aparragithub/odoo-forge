from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError

from odoo_forge.manifest.schema import (
    DEFAULT_ODOO_BIND_HOST,
    BackendConfig,
    CoreLayer,
    GitLayer,
    GitRepo,
    Layer,
    Manifest,
    OdooBackendConfig,
    PublishedLayer,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _base_manifest_kwargs() -> dict[str, object]:
    return {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": {"addons_path": "client/addons"},
    }


def test_manifest_requires_core_field() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    assert isinstance(manifest.core, CoreLayer)


def test_manifest_workspace_defaults_to_none() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    assert manifest.workspace is None


def test_manifest_workspace_accepts_checkout_timeout_seconds() -> None:
    manifest = Manifest.model_validate(
        {
            **_base_manifest_kwargs(),
            "workspace": {"checkout_timeout_seconds": 300},
        }
    )

    assert manifest.workspace is not None
    assert manifest.workspace.checkout_timeout_seconds == 300


def test_manifest_backend_defaults_to_none() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    assert manifest.backend is None


def test_manifest_backend_accepts_optional_odoo_http_port() -> None:
    manifest = Manifest.model_validate(
        {
            **_base_manifest_kwargs(),
            "backend": {"odoo": {"http_port": 18069}},
        }
    )

    assert manifest.backend == BackendConfig(odoo=OdooBackendConfig(http_port=18069))


def test_manifest_backend_odoo_bind_host_defaults_to_loopback() -> None:
    Manifest.model_validate(_base_manifest_kwargs())

    assert OdooBackendConfig().bind_host == DEFAULT_ODOO_BIND_HOST


def test_manifest_backend_accepts_valid_ipv4_bind_host() -> None:
    manifest = Manifest.model_validate(
        {**_base_manifest_kwargs(), "backend": {"odoo": {"bind_host": "192.168.1.20"}}}
    )

    assert manifest.backend is not None
    assert manifest.backend.odoo is not None
    assert manifest.backend.odoo.bind_host == "192.168.1.20"


@pytest.mark.parametrize("bind_host", ["odoo.local", "::1", " 192.168.1.20 "])
def test_manifest_backend_rejects_non_ipv4_bind_host(bind_host: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(
            {**_base_manifest_kwargs(), "backend": {"odoo": {"bind_host": bind_host}}}
        )

    assert exc_info.value.errors()[0]["loc"] == ("backend", "odoo", "bind_host")


def test_manifest_backend_rejects_invalid_odoo_http_port() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(
            {
                **_base_manifest_kwargs(),
                "backend": {"odoo": {"http_port": 70000}},
            }
        )

    assert exc_info.value.errors()[0]["loc"] == ("backend", "odoo", "http_port")


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
    git_layer = GitLayer(
        type="git", name="localization", repos=[repo], requires_edition="enterprise"
    )
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
    layer_adapter: TypeAdapter[Layer] = TypeAdapter(Layer)
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
        "client": {
            "addons_path": "client/addons",
            "python_requirements": "client/requirements.txt",
        },
        "overrides": [
            {
                "layer": "localization",
                "repo": "odoo-argentina-ee",
                "fork": "https://github.com/acme/fork.git",
                "ref": "custom",
            },
        ],
    }

    manifest = Manifest.model_validate(manifest_dict)

    assert manifest.name == "odoo-idp"
    assert manifest.client.addons_path == Path("client/addons")
    assert len(manifest.layers) == 2
    assert isinstance(manifest.layers[0], PublishedLayer)
    assert isinstance(manifest.layers[1], GitLayer)
    assert manifest.overrides[0].repo == "odoo-argentina-ee"


def test_git_layer_category_defaults_to_none() -> None:
    """Additive optional field: absent `category` (legacy Slice 1/2a/2b
    fixtures) must still validate, defaulting to `None`."""
    layer = GitLayer(
        type="git",
        name="localization",
        repos=[GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
    )

    assert layer.category is None


def test_git_layer_accepts_explicit_category() -> None:
    layer = GitLayer(
        type="git",
        name="localization",
        repos=[GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
        category="localization",
    )

    assert layer.category == "localization"


def test_published_layer_category_defaults_to_none() -> None:
    layer = PublishedLayer(
        type="published",
        name="enterprise",
        source="registry://example/odoo-ee",
        version="19.0.1",
    )

    assert layer.category is None


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
