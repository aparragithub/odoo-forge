from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError

from odoo_forge.manifest.schema import (
    DEFAULT_ODOO_BIND_HOST,
    BackendConfig,
    CoreLayer,
    EnterpriseLayer,
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


def test_requires_enterprise_on_layer_defaults_to_false() -> None:
    repo = GitRepo(url="https://github.com/ingadhoc/odoo-argentina-ee.git", ref="19.0")
    git_layer = GitLayer(type="git", name="localization", repos=[repo])
    published_layer = PublishedLayer(
        type="published",
        name="enterprise",
        source="registry://example/odoo-ee",
        version="19.0.1",
    )

    assert git_layer.requires_enterprise is False
    assert published_layer.requires_enterprise is False


def test_requires_enterprise_true_on_git_and_published_layer() -> None:
    repo = GitRepo(url="https://github.com/ingadhoc/odoo-argentina-ee.git", ref="19.0")
    git_layer = GitLayer(type="git", name="localization", repos=[repo], requires_enterprise=True)
    published_layer = PublishedLayer(
        type="published",
        name="enterprise",
        source="registry://example/odoo-ee",
        version="19.0.1",
        requires_enterprise=True,
    )

    assert git_layer.requires_enterprise is True
    assert published_layer.requires_enterprise is True


def test_git_repo_rejects_legacy_requires_edition_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        GitRepo.model_validate(
            {
                "url": "https://github.com/ingadhoc/odoo-argentina-ee.git",
                "ref": "19.0",
                "requires_edition": "enterprise",
            }
        )

    assert "requires_enterprise" in str(exc_info.value)


def test_git_layer_rejects_legacy_requires_edition_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        GitLayer.model_validate(
            {
                "type": "git",
                "name": "localization",
                "repos": [],
                "requires_edition": "enterprise",
            }
        )

    assert "requires_enterprise" in str(exc_info.value)


def test_published_layer_rejects_legacy_requires_edition_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PublishedLayer.model_validate(
            {
                "type": "published",
                "name": "enterprise",
                "source": "registry://example/odoo-ee",
                "version": "19.0.1",
                "requires_edition": "enterprise",
            }
        )

    assert "requires_enterprise" in str(exc_info.value)


def test_enterprise_edition_requires_enterprise_block() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate({**_base_manifest_kwargs(), "edition": "enterprise"})

    assert "enterprise" in str(exc_info.value)


def test_community_edition_forbids_enterprise_block() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(
            {
                **_base_manifest_kwargs(),
                "edition": "community",
                "enterprise": {"url": "https://github.com/odoo/enterprise.git", "ref": "19.0"},
            }
        )

    assert "enterprise" in str(exc_info.value)


def test_enterprise_edition_with_valid_enterprise_block_succeeds() -> None:
    manifest = Manifest.model_validate(
        {
            **_base_manifest_kwargs(),
            "edition": "enterprise",
            "enterprise": {"url": "https://github.com/odoo/enterprise.git", "ref": "19.0"},
        }
    )

    assert isinstance(manifest.enterprise, EnterpriseLayer)
    assert manifest.enterprise.url == "https://github.com/odoo/enterprise.git"
    assert manifest.enterprise.ref == "19.0"
    assert manifest.enterprise.type == "enterprise"


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
        "enterprise": {"url": "https://github.com/odoo/enterprise.git", "ref": "19.0"},
        "layers": [
            {
                "type": "published",
                "name": "enterprise-addons",
                "source": "registry://example/odoo-ee",
                "version": "19.0.1",
                "requires_enterprise": True,
            },
            {
                "type": "git",
                "name": "localization",
                "repos": [
                    {
                        "url": "https://github.com/ingadhoc/odoo-argentina-ee.git",
                        "ref": "19.0",
                    }
                ],
                "requires_enterprise": True,
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


def test_git_layer_category_defaults_to_custom() -> None:
    """Absent `category` must validate and default to `"custom"` (Slice 2:
    open categories, validated free string). Under the pure mount model this
    resolves to `/mnt/custom/default/` in projection, not a system root."""
    layer = GitLayer(
        type="git",
        name="localization",
        repos=[GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
    )

    assert layer.category == "custom"


def test_git_layer_accepts_explicit_category() -> None:
    layer = GitLayer(
        type="git",
        name="localization",
        repos=[GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
        category="localization",
    )

    assert layer.category == "localization"


def test_git_layer_accepts_a_category_matching_a_system_root_name() -> None:
    """Slice 2 (pure mount model): NO reserved-name blocklist. A user layer
    declaring `category: community` is just a plain `/mnt/custom/community`
    subfolder — it can never collide with the system `community` root,
    because user layers never target system roots at all."""
    layer = GitLayer(
        type="git",
        name="localization",
        repos=[GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
        category="community",
    )

    assert layer.category == "community"


@pytest.mark.parametrize(
    "category",
    [
        "../etc",
        "a/b",
        "Uppercase",
        "-leading-hyphen",
        "trailing-hyphen-",
        "",
        "a" * 64,
    ],
)
def test_git_layer_rejects_invalid_category_slug(category: str) -> None:
    with pytest.raises(ValidationError):
        GitLayer(
            type="git",
            name="localization",
            repos=[GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0")],
            category=category,
        )


def test_published_layer_category_defaults_to_custom() -> None:
    layer = PublishedLayer(
        type="published",
        name="enterprise",
        source="registry://example/odoo-ee",
        version="19.0.1",
    )

    assert layer.category == "custom"


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
    assert manifest.layers[1].requires_enterprise is True


def test_malformed_fixture_yields_single_scoped_error() -> None:
    raw = yaml.safe_load((FIXTURES_DIR / "malformed.project.yaml").read_text())

    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(raw)

    errors = exc_info.value.errors()
    layer_errors = [e for e in errors if e["loc"][0] == "layers"]
    assert len(layer_errors) == 1
    assert layer_errors[0]["loc"][2] == "git"


def _priority_layers() -> list[dict[str, object]]:
    return [
        {
            "type": "git",
            "name": "ov",
            "category": "overrides",
            "repos": [{"url": "https://github.com/acme/ov.git", "ref": "19.0"}],
        },
    ]


def test_mount_priority_defaults_to_empty_list() -> None:
    manifest = Manifest.model_validate(_base_manifest_kwargs())

    assert manifest.mount_priority == []


def test_mount_priority_accepts_known_system_and_custom_roots() -> None:
    manifest = Manifest.model_validate(
        {
            **_base_manifest_kwargs(),
            "layers": _priority_layers(),
            "mount_priority": ["custom/overrides", "worktrees", "community", "enterprise"],
        }
    )

    assert manifest.mount_priority == [
        "custom/overrides",
        "worktrees",
        "community",
        "enterprise",
    ]


def test_mount_priority_uncategorized_layer_key_is_custom_default() -> None:
    manifest = Manifest.model_validate(
        {
            **_base_manifest_kwargs(),
            "layers": [
                {
                    "type": "git",
                    "name": "x",
                    "repos": [{"url": "https://github.com/acme/x.git", "ref": "19.0"}],
                }
            ],
            "mount_priority": ["custom/default"],
        }
    )

    assert manifest.mount_priority == ["custom/default"]


def test_mount_priority_rejects_unknown_custom_root() -> None:
    with pytest.raises(ValidationError, match="mount_priority"):
        Manifest.model_validate(
            {
                **_base_manifest_kwargs(),
                "layers": _priority_layers(),
                "mount_priority": ["custom/nope"],
            }
        )


def test_mount_priority_rejects_system_root_typo() -> None:
    # `localization` is no longer a system root (pure mount model); it is only
    # valid as `custom/localization` and only when actually declared.
    with pytest.raises(ValidationError, match="mount_priority"):
        Manifest.model_validate({**_base_manifest_kwargs(), "mount_priority": ["localization"]})


def test_mount_priority_rejects_duplicate_entries() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Manifest.model_validate(
            {**_base_manifest_kwargs(), "mount_priority": ["community", "community"]}
        )
