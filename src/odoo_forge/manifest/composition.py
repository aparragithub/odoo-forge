"""Pure onion composition: ordering + validation, zero I/O.

`compose(manifest)` returns the ordered chain
`core -> enterprise -> layers... -> client` (the enterprise singleton is
inserted at chain position 2 only when present) after validating reserved
layer names, `PublishedLayer` edition coherence, and override targets. Never
touches the filesystem or network.

Edition coherence for `GitLayer` (a community manifest whose dependency
chain reaches an Enterprise-only module) is no longer checked here — it is
validated later, against the materialized addons_path, by the
`module-dependency-validation` capability (see
`odoo_forge.manifest.module_deps`). `PublishedLayer` content is never
git-checked-out, so that real validator can never see it; its edition
coherence is still checked here, scoped to `PublishedLayer` only, via the
restored `requires_enterprise` flag (see
`_check_published_layer_edition_coherence`).
"""

from odoo_forge.manifest.errors import CompositionError
from odoo_forge.manifest.schema import (
    Client,
    CoreLayer,
    EnterpriseLayer,
    GitLayer,
    Layer,
    Manifest,
    PublishedLayer,
)


def compose(manifest: Manifest) -> list[CoreLayer | EnterpriseLayer | Layer | Client]:
    _check_reserved_layer_names(manifest)
    _check_published_layer_edition_coherence(manifest)
    _check_overrides(manifest)

    chain: list[CoreLayer | EnterpriseLayer | Layer | Client] = [manifest.core]
    if manifest.enterprise is not None:
        chain.append(manifest.enterprise)
    chain.extend(manifest.layers)
    chain.append(manifest.client)
    return chain


def _check_reserved_layer_names(manifest: Manifest) -> None:
    if any(layer.name == "core" for layer in manifest.layers):
        raise CompositionError("layer name 'core' is reserved for the singleton core layer")


def _check_published_layer_edition_coherence(manifest: Manifest) -> None:
    """Reject a community manifest declaring a `PublishedLayer` that flags
    itself `requires_enterprise`. Scoped to `PublishedLayer` ONLY —
    `GitLayer` has no `requires_enterprise` field anymore (rejected at parse
    time via `extra="forbid"`) and is instead covered by the real
    module-dependency validator once its content is materialized."""
    if manifest.edition == "enterprise":
        return

    for layer in manifest.layers:
        if isinstance(layer, PublishedLayer) and layer.requires_enterprise:
            raise CompositionError(
                f"layer '{layer.name}' requires enterprise edition "
                "but manifest edition is 'community'"
            )


def _check_overrides(manifest: Manifest) -> None:
    layers_by_name = {layer.name: layer for layer in manifest.layers}
    targets: set[tuple[str, str]] = set()

    for override in manifest.overrides:
        if override.layer == "core":
            raise CompositionError("override cannot target the reserved core layer")

        target = (override.layer, override.repo)
        if target in targets:
            raise CompositionError(
                f"duplicate override for repo '{override.repo}' in layer '{override.layer}'"
            )
        targets.add(target)

        layer = layers_by_name.get(override.layer)
        if layer is None:
            raise CompositionError(f"override references unknown layer '{override.layer}'")

        if isinstance(layer, GitLayer):
            repo_urls = {repo.url for repo in layer.repos}
            if override.repo not in repo_urls:
                raise CompositionError(
                    f"override references unknown repo '{override.repo}' "
                    f"in layer '{override.layer}'"
                )
        else:
            raise CompositionError(
                f"override for layer '{override.layer}' specifies repo "
                f"'{override.repo}', but that layer has no repos (not a git layer)"
            )


__all__ = ["compose"]
