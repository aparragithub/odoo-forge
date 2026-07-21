from pathlib import Path

import pytest

from odoo_forge.manifest.artifacts import PublishedArtifactResolution
from odoo_forge.manifest.errors import CompositionError, RefNotFoundError
from odoo_forge.manifest.lockfile import (
    ResolvedPublishedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.locking import build_lock
from odoo_forge.manifest.schema import (
    Client,
    CoreLayer,
    EnterpriseLayer,
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


class _FakePublishedArtifactResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def resolve(self, source: str, version: str) -> PublishedArtifactResolution:
        self.calls.append((source, version))
        return PublishedArtifactResolution(source, version, "sha256:" + "a" * 64)


def _manifest(**overrides: object) -> Manifest:
    defaults: dict[str, object] = {
        "name": "odoo-idp",
        "odoo_version": "19.0",
        "edition": "community",
        "client": Client(addons_path=Path("client/addons")),
    }
    defaults.update(overrides)
    return Manifest(**defaults)  # type: ignore[arg-type]


def test_core_ref_none_resolves_via_default_before_provider() -> None:
    manifest = _manifest(core=CoreLayer())
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    assert provider.calls[0] == (manifest.core.url, "19.0")
    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].ref == "19.0"
    assert core_layer.repos[0].commit == "sha-19.0"


def test_explicit_core_ref_used_directly() -> None:
    manifest = _manifest(core=CoreLayer(ref="17.0-custom"))
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

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

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

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

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    assert [layer.name for layer in lock.layers] == ["core", "localization", "extras"]

    core_layer = next(layer for layer in lock.layers if layer.name == "core")
    assert core_layer.repos[0].commit == "sha-19.0"

    localization = next(layer for layer in lock.layers if layer.name == "localization")
    assert localization.repos[0].url == "https://github.com/ingadhoc/odoo-partner.git"
    assert localization.repos[0].commit == "sha-19.0"

    extras = next(layer for layer in lock.layers if layer.name == "extras")
    assert extras.repos[0].url == "https://github.com/acme/odoo-extras.git"
    assert extras.repos[0].commit == "sha-feature-y"


def test_override_replaces_git_source_and_ref_before_resolution() -> None:
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
                repo="https://github.com/ingadhoc/odoo-argentina-ee.git",
                fork="https://github.com/acme/odoo-argentina-ee.git",
                ref="custom-fix",
            )
        ],
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    localization = next(layer for layer in lock.layers if layer.name == "localization")
    assert localization.repos[0].url == "https://github.com/acme/odoo-argentina-ee.git"
    assert localization.repos[0].ref == "custom-fix"
    assert localization.repos[0].commit == "sha-custom-fix"
    assert provider.calls == [
        (manifest.core.url, "19.0"),
        ("https://github.com/acme/odoo-argentina-ee.git", "custom-fix"),
    ]


def test_lock_pins_published_digest_and_effective_git_override_together() -> None:
    manifest = _manifest(
        layers=[
            PublishedLayer(
                type="published",
                name="enterprise",
                source="registry://example/odoo-ee",
                version="19.0",
            ),
            GitLayer(
                type="git",
                name="localization",
                repos=[GitRepo(url="https://example.com/localization.git", ref="19.0")],
            ),
        ],
        overrides=[
            Override(
                layer="localization",
                repo="https://example.com/localization.git",
                fork="https://example.com/fork.git",
                ref="fix-19.0",
            )
        ],
    )
    provider = _FakeSourceProvider()
    artifacts = _FakePublishedArtifactResolver()

    lock = build_lock(manifest, provider, artifacts)

    assert artifacts.calls == [("registry://example/odoo-ee", "19.0")]
    assert lock.published_layers == [
        ResolvedPublishedLayer(
            name="enterprise",
            source="registry://example/odoo-ee",
            version="19.0",
            digest="sha256:" + "a" * 64,
        )
    ]
    localization = next(layer for layer in lock.git_layers if layer.name == "localization")
    assert localization.repos[0].model_dump() == {
        "url": "https://example.com/fork.git",
        "ref": "fix-19.0",
        "commit": "sha-fix-19.0",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        [
            Override(
                layer="missing",
                repo="https://example/missing.git",
                fork="https://acme/fork.git",
                ref="x",
            )
        ],
        [
            Override(
                layer="core",
                repo="https://github.com/odoo/odoo.git",
                fork="https://acme/fork.git",
                ref="x",
            )
        ],
        [
            Override(
                layer="extra",
                repo="https://example/extra.git",
                fork="https://acme/one.git",
                ref="one",
            ),
            Override(
                layer="extra",
                repo="https://example/extra.git",
                fork="https://acme/two.git",
                ref="two",
            ),
        ],
    ],
)
def test_structurally_invalid_override_never_calls_provider(overrides: list[Override]) -> None:
    manifest = _manifest(
        layers=[
            GitLayer(
                type="git",
                name="extra",
                repos=[GitRepo(url="https://example/extra.git", ref="19.0")],
            )
        ],
        overrides=overrides,
    )
    provider = _FakeSourceProvider()

    with pytest.raises(CompositionError):
        build_lock(manifest, provider, _FakePublishedArtifactResolver())

    assert provider.calls == []


def test_core_shadowing_is_rejected_before_any_provider_call() -> None:
    manifest = _manifest(
        layers=[
            GitLayer(
                type="git",
                name="core",
                repos=[GitRepo(url="https://example.com/shadow.git", ref="main")],
            )
        ],
        overrides=[
            Override(
                layer="core",
                repo="https://example.com/shadow.git",
                fork="https://example.com/fork.git",
                ref="custom",
            )
        ],
    )
    provider = _FakeSourceProvider()

    with pytest.raises(CompositionError, match="reserved"):
        build_lock(manifest, provider, _FakePublishedArtifactResolver())

    assert provider.calls == []


def test_published_layers_omitted_from_lock() -> None:
    manifest = _manifest(
        edition="enterprise",
        enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="19.0"),
        layers=[
            PublishedLayer(
                type="published",
                name="enterprise",
                source="registry://example/odoo-ee",
                version="19.0.1",
                requires_enterprise=True,
            )
        ],
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    # The `PublishedLayer` named "enterprise" is never resolved into a git
    # layer — only the `EnterpriseLayer` singleton is (as its own
    # `git_layers` entry, distinct from `lock.published_layers`).
    assert lock.published_layers[0].name == "enterprise"
    assert [layer.name for layer in lock.layers] == ["core", "enterprise"]
    assert provider.calls == [
        (manifest.core.url, "19.0"),
        ("https://github.com/odoo/enterprise.git", "19.0"),
    ]


def test_enterprise_layer_resolved_into_a_dedicated_git_layer() -> None:
    manifest = _manifest(
        edition="enterprise",
        enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git"),
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    enterprise_layer = next(layer for layer in lock.git_layers if layer.name == "enterprise")
    assert enterprise_layer.repos == [
        ResolvedRepo(
            url="https://github.com/odoo/enterprise.git",
            ref="19.0",
            commit="sha-19.0",
        )
    ]
    assert provider.calls == [
        (manifest.core.url, "19.0"),
        ("https://github.com/odoo/enterprise.git", "19.0"),
    ]


def test_explicit_enterprise_ref_used_directly() -> None:
    manifest = _manifest(
        edition="enterprise",
        enterprise=EnterpriseLayer(url="https://github.com/odoo/enterprise.git", ref="17.0-custom"),
    )
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    enterprise_layer = next(layer for layer in lock.git_layers if layer.name == "enterprise")
    assert enterprise_layer.repos[0].ref == "17.0-custom"
    assert enterprise_layer.repos[0].commit == "sha-17.0-custom"


def test_no_enterprise_layer_added_when_manifest_enterprise_is_none() -> None:
    manifest = _manifest()
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

    assert all(layer.name != "enterprise" for layer in lock.git_layers)
    assert provider.calls == [(manifest.core.url, "19.0")]


def test_generated_from_matches_manifest_hash() -> None:
    manifest = _manifest()
    provider = _FakeSourceProvider()

    lock = build_lock(manifest, provider, _FakePublishedArtifactResolver())

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
                requires_enterprise=True,
            )
        ],
    )
    provider = _FakeSourceProvider()

    with pytest.raises(CompositionError):
        build_lock(manifest, provider, _FakePublishedArtifactResolver())

    assert provider.calls == []


def test_resolution_error_propagates_uncaught() -> None:
    manifest = _manifest(core=CoreLayer())

    class _FailingProvider:
        def resolve_ref(self, url: str, ref: str) -> str:
            raise RefNotFoundError(url, ref)

    with pytest.raises(RefNotFoundError):
        build_lock(manifest, _FailingProvider(), _FakePublishedArtifactResolver())
