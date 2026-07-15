"""Pure `build_lock` use case: manifest + `SourceProvider` -> `Lockfile`.

Depends only on the `SourceProvider` Protocol, never a concrete adapter — this
keeps the module import-pure (see the 3rd import-linter contract forbidding
`odoo_forge` from importing `odoo_forge_git`). Resolution failures
(`ResolutionError` family) and composition failures (`CompositionError`) are
never caught here; they propagate to the caller (the CLI boundary).
"""

from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.lockfile import (
    Lockfile,
    ResolvedLayer,
    ResolvedPublishedLayer,
    ResolvedRepo,
    compute_manifest_hash,
)
from odoo_forge.manifest.resolution import resolve_default_ref
from odoo_forge.manifest.schema import GitLayer, Manifest, Override, PublishedLayer
from odoo_forge.ports.published_artifact_resolver import PublishedArtifactResolver
from odoo_forge.ports.source_provider import SourceProvider


def build_lock(
    manifest: Manifest,
    provider: SourceProvider,
    artifact_resolver: PublishedArtifactResolver,
) -> Lockfile:
    # Coherence gate first: an incoherent manifest must never trigger a
    # network/subprocess call before it is rejected.
    compose(manifest)

    git_layers: list[ResolvedLayer] = [_resolve_core(manifest, provider)]
    published_layers: list[ResolvedPublishedLayer] = []

    overrides = {(override.layer, override.repo): override for override in manifest.overrides}
    for layer in manifest.layers:
        if isinstance(layer, GitLayer):
            git_layers.append(_resolve_git_layer(layer, provider, overrides))
        elif isinstance(layer, PublishedLayer):
            resolution = artifact_resolver.resolve(layer.source, layer.version)
            published_layers.append(
                ResolvedPublishedLayer(
                    name=layer.name,
                    source=resolution.source,
                    version=resolution.version,
                    digest=resolution.digest,
                )
            )

    return Lockfile(
        generated_from=compute_manifest_hash(manifest),
        git_layers=git_layers,
        published_layers=published_layers,
    )


def _resolve_core(manifest: Manifest, provider: SourceProvider) -> ResolvedLayer:
    core = manifest.core
    ref = resolve_default_ref(core, manifest.odoo_version)
    commit = provider.resolve_ref(core.url, ref)
    return ResolvedLayer(
        name="core",
        repos=[ResolvedRepo(url=core.url, ref=ref, commit=commit)],
    )


def _resolve_git_layer(
    layer: GitLayer, provider: SourceProvider, overrides: dict[tuple[str, str], Override]
) -> ResolvedLayer:
    repos = [
        _resolve_repo(layer.name, repo.url, repo.ref, provider, overrides)
        for repo in layer.repos
    ]
    return ResolvedLayer(name=layer.name, repos=repos)


def _resolve_repo(
    layer_name: str,
    url: str,
    ref: str,
    provider: SourceProvider,
    overrides: dict[tuple[str, str], Override],
) -> ResolvedRepo:
    override = overrides.get((layer_name, url))
    effective_url = override.fork if override is not None else url
    effective_ref = override.ref if override is not None else ref
    return ResolvedRepo(
        url=effective_url,
        ref=effective_ref,
        commit=provider.resolve_ref(effective_url, effective_ref),
    )


__all__ = ["build_lock"]
