import pytest

from odoo_forge.manifest.errors import CompositionError, RefNotFoundError
from odoo_forge.manifest.lockfile import compute_manifest_hash
from odoo_forge.manifest.locking import build_lock
from odoo_forge.manifest.schema import (
    Client,
    CoreLayer,
    GitLayer,
    GitRepo,
    Manifest,
    Override,
    PublishedLayer,
)


class _FakeSourceProvider:
    """Deterministic, network-free `SourceProvider` test double."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def resolve_ref(self, url: str, ref: str) -> str:
        self.calls.append((url, ref))
        return f"sha-{ref}"


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path="client/addons"),
    }
    defaults.update(overrides)
    return Manifest(**defaults)  # type: ignore[arg-type]


def test_core_ref_none_resolves_via_default_before_provider() -> None:
    manifest = _manifest(core=CoreLayer())
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    assert provider.calls[0] == (manifest.core.url, "19.0")
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].ref == "19.0"
    assert core_layer.repos[0].commit == "sha-19.0"


def test_explicit_core_ref_used_directly() -> None:
    manifest = _manifest(core=CoreLayer(ref="17.0-custom"))
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    assert provider.calls[0] == (manifest.core.url, "17.0-custom")
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].ref == "17.0-custom"
    assert core_layer.repos[0].commit == "sha-17.0-custom"


def test_git_layers_mapped_to_resolved_repos() -> None:
    """Each repo in a `GitLayer` must be pinned to ITS OWN ref's SHA — using
    distinct refs per repo here would surface a url/ref/sha swap or an
    off-by-one in the mapping that identical refs (e.g. both "19.0") cannot."""
    manifest = _manifest(
        layers=[
            GitLayer(
                type="git",
                name="localization",
                repos=[
                    GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0"),
                    GitRepo(url="https://github.com/ingadhoc/odoo-sale.git", ref="feature-x"),
                ],
            )
        ]
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    localization = next(layer for layer in lock.layers if layer.name == "localization")
    assert [(repo.url, repo.ref, repo.commit) for repo in localization.repos] == [
        ("https://github.com/ingadhoc/odoo-partner.git", "19.0", "sha-19.0"),
        ("https://github.com/ingadhoc/odoo-sale.git", "feature-x", "sha-feature-x"),
    ]


def test_multiple_git_layers_each_pinned_correctly_no_cross_attribution() -> None:
    """With core + two distinct `GitLayer`s (distinct names and refs), every
    layer must be pinned to its own correct SHA — none skipped, none
    misattributed to another layer."""
    manifest = _manifest(
        layers=[
            GitLayer(
                type="git",
                name="localization",
                repos=[
                    GitRepo(url="https://github.com/ingadhoc/odoo-partner.git", ref="19.0"),
                ],
            ),
            GitLayer(
                type="git",
                name="extras",
                repos=[
                    GitRepo(url="https://github.com/acme/odoo-extras.git", ref="feature-y"),
                ],
            ),
        ]
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    assert [layer.name for layer in lock.layers] == ["core", "localization", "extras"]

    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].commit == "sha-19.0"

    localization = next(layer for layer in lock.layers if layer.name == "localization")
    assert localization.repos[0].url == "https://github.com/ingadhoc/odoo-partner.git"
    assert localization.repos[0].commit == "sha-19.0"

    extras = next(layer for layer in lock.layers if layer.name == "extras")
    assert extras.repos[0].url == "https://github.com/acme/odoo-extras.git"
    assert extras.repos[0].commit == "sha-feature-y"


def test_override_not_applied_pins_original_repo_ref() -> None:
    """A manifest `Override` (fork url + custom ref) must NOT be applied by
    `build_lock` — override application is deferred past Slice 2b. The
    original repo's url/ref is resolved and pinned, not the fork's."""
    manifest = _manifest(
        layers=[
            GitLayer(
                type="git",
                name="localization",
                repos=[
                    GitRepo(url="https://github.com/ingadhoc/odoo-argentina-ee.git", ref="19.0"),
                ],
            ),
        ],
        overrides=[
            Override(
                layer="localization",
                repo="odoo-argentina-ee",
                fork="https://github.com/acme/odoo-argentina-ee.git",
                ref="custom-fix",
            )
        ],
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    localization = next(layer for layer in lock.layers if layer.name == "localization")
    assert localization.repos[0].url == "https://github.com/ingadhoc/odoo-argentina-ee.git"
    assert localization.repos[0].ref == "19.0"
    assert localization.repos[0].commit == "sha-19.0"
    assert ("https://github.com/acme/odoo-argentina-ee.git", "custom-fix") not in provider.calls


def test_published_layers_omitted_from_lock() -> None:
    manifest = _manifest(
        edition="enterprise",
        layers=[
            PublishedLayer(
                type="published",
                name="enterprise",
                source="registry://example/odoo-ee",
                version="19.0.1",
                requires_edition="enterprise",
            )
        ],
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    assert all(layer.name != "enterprise" for layer in lock.layers)
    # Only the core layer is resolved — the published layer never calls the provider.
    assert provider.calls == [(manifest.core.url, "19.0")]


def test_generated_from_matches_manifest_hash() -> None:
    manifest = _manifest()
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider)

    assert lock.generated_from == compute_manifest_hash(manifest)


def test_composition_error_propagates_before_resolution() -> None:
    manifest = _manifest(
        edition="community",
        layers=[
            PublishedLayer(
                type="published",
                name="enterprise",
                source="registry://example/odoo-ee",
                version="19.0.1",
                requires_edition="enterprise",
            )
        ],
    )
    provider = _FakeSourceProvider()

    with pytest.raises(CompositionError):
        build_lock(manifest, provider)

    assert provider.calls == []


def test_resolution_error_propagates_uncaught() -> None:
    manifest = _manifest(core=CoreLayer())

    class _FailingProvider:
        def resolve_ref(self, url: str, ref: str) -> str:
            raise RefNotFoundError(url, ref)

    with pytest.raises(RefNotFoundError):
        build_lock(manifest, _FailingProvider())
