"""Pure onion composition: ordering + coherence validation, zero I/O.

`compose(manifest)` returns the ordered chain `core -> layers... -> client`
after validating edition coherence and override targets. Never touches the
filesystem or network.
"""

from odoo_forge.manifest.errors import CompositionError
from odoo_forge.manifest.schema import Client, CoreLayer, GitLayer, Layer, Manifest


def compose(manifest: Manifest) -> list[CoreLayer | Layer | Client]:
    _check_edition_coherence(manifest)
    _check_overrides(manifest)

    chain: list[CoreLayer | Layer | Client] = [manifest.core]
    chain.extend(manifest.layers)
    chain.append(manifest.client)
    return chain


def _check_edition_coherence(manifest: Manifest) -> None:
    if manifest.edition == "enterprise":
        return

    for layer in manifest.layers:
        if layer.requires_edition == "enterprise":
            raise CompositionError(
                f"layer '{layer.name}' requires enterprise edition but manifest edition is 'community'"
            )
        if isinstance(layer, GitLayer):
            for repo in layer.repos:
                if repo.requires_edition == "enterprise":
                    raise CompositionError(
                        f"repo '{repo.url}' in layer '{layer.name}' requires enterprise edition "
                        "but manifest edition is 'community'"
                    )


def _check_overrides(manifest: Manifest) -> None:
    layers_by_name = {layer.name: layer for layer in manifest.layers}

    for override in manifest.overrides:
        layer = layers_by_name.get(override.layer)
        if layer is None:
            raise CompositionError(f"override references unknown layer '{override.layer}'")

        if isinstance(layer, GitLayer):
            repo_urls = {_repo_name(repo.url) for repo in layer.repos}
            if override.repo not in repo_urls:
                raise CompositionError(
                    f"override references unknown repo '{override.repo}' in layer '{override.layer}'"
                )


def _repo_name(url: str) -> str:
    """Return the repo name used to match `Override.repo` against a git URL.

    Convention: the URL basename with any trailing slash and `.git` suffix
    removed. For example ``https://github.com/ingadhoc/odoo-partner.git`` ->
    ``odoo-partner``.

    Edge case: this is a basename, not a fully-qualified path, so two repos
    from different owners with the same last path segment (e.g.
    ``acme/odoo-web`` and ``ingadhoc/odoo-web``) collapse to the same name and
    cannot be distinguished by an override. This is acceptable within a single
    layer today; disambiguation is deferred to a later slice if needed.
    """
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


__all__ = ["compose"]
