"""Pure onion composition: ordering + coherence validation, zero I/O.

`compose(manifest)` returns the ordered chain
`core -> enterprise -> layers... -> client` (the enterprise singleton is
inserted at chain position 2 only when present) after validating edition
coherence and override targets. Never touches the filesystem or network.
"""

from odoo_forge.manifest.errors import CompositionError
from odoo_forge.manifest.schema import Client, CoreLayer, EnterpriseLayer, GitLayer, Layer, Manifest


def compose(manifest: Manifest) -> list[CoreLayer | EnterpriseLayer | Layer | Client]:
    _check_reserved_layer_names(manifest)
    _check_edition_coherence(manifest)
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


def _check_edition_coherence(manifest: Manifest) -> None:
    if manifest.edition == "enterprise":
        return

    for layer in manifest.layers:
        if layer.requires_enterprise:
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
