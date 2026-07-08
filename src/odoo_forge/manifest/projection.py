"""Pure workspace projection planning: manifest + lock -> filesystem plan.

`classify_root` and `plan_projection` are the pure, provider-free half of
the Slice 3 projection pipeline. The lock already carries resolved commits
(pinned by `build_lock`), so no `SourceProvider`/`WorkspaceProvider` I/O is
needed here — this module performs zero I/O and never raises anything
except the typed `ProjectionError`.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Mapping

from pydantic import BaseModel

from odoo_forge.manifest.errors import ProjectionError, ScanError
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.schema import CoreLayer, GitLayer, Manifest, PublishedLayer
from odoo_forge.manifest.state import MaterializedLayer, MaterializedRepo, MaterializedState

if TYPE_CHECKING:
    from odoo_forge.ports.workspace_provider import WorkspaceProvider

# Fixed 5-root table. `worktrees` is reserved exclusively for `unlock`-promoted
# writable copies and is NEVER returned by `classify_root` — read-only
# projection only ever targets the other 4 roots.
MountRoot = Literal["custom", "community", "localization", "enterprise"]

MOUNT_ROOTS: dict[MountRoot | Literal["worktrees"], Path] = {
    "community": Path("/mnt/community"),
    "custom": Path("/mnt/custom"),
    "localization": Path("/mnt/localization"),
    "enterprise": Path("/mnt/enterprise"),
    "worktrees": Path("/mnt/worktrees"),
}


class ScannedRepo(BaseModel):
    """Raw, un-interpreted result of scanning one on-disk checkout.

    Emitted by a `WorkspaceProvider.scan` adapter (later slice) straight
    from `git -C <path> rev-parse HEAD` / `remote.origin.url` — no layer
    attribution yet. `materialize_state` (later slice) maps a list of these
    back into a `MaterializedState` using the mount-root/directory
    convention written by `project_workspace`.
    """

    path: Path
    url: str
    commit: str


class WorkspacePlanEntry(BaseModel):
    mount_root: MountRoot
    layer: str
    url: str
    commit: str
    target_path: Path


class WorkspacePlan(BaseModel):
    steps: list[WorkspacePlanEntry] = []


class UnlockPlan(BaseModel):
    """Core-computed promotion target for `unlock`. Pure, zero I/O."""

    source: Path
    dest: Path
    branch: str


def classify_root(layer: CoreLayer | GitLayer | PublishedLayer) -> MountRoot:
    """Map a layer to its read-only projection mount root. Pure, zero I/O.

    Precedence: `CoreLayer` always classifies to `"community"`; else
    `requires_edition == "enterprise"` always wins over any explicit
    `category`; else the layer's explicit `category` when set; else
    `"custom"` as the default. Never returns `"worktrees"`.
    """
    if isinstance(layer, CoreLayer):
        return "community"
    if layer.requires_edition == "enterprise":
        return "enterprise"
    if layer.category is not None:
        return layer.category
    return "custom"


def plan_projection(manifest: Manifest, lock: Lockfile) -> WorkspacePlan:
    """Join `lock.layers` to the current manifest by name and classify each
    to a mount root, preserving `lock.layers` order. Pure, zero I/O.

    Raises `ProjectionError` naming the orphaned layer when a locked layer
    has no matching manifest layer — no partial plan is ever returned.
    """
    manifest_layers_by_name: dict[str, CoreLayer | GitLayer | PublishedLayer] = {
        "core": manifest.core,
    }
    for layer in manifest.layers:
        manifest_layers_by_name[layer.name] = layer

    steps: list[WorkspacePlanEntry] = []
    for lock_layer in lock.layers:
        layer = manifest_layers_by_name.get(lock_layer.name)
        if layer is None:
            raise ProjectionError(
                f"locked layer '{lock_layer.name}' has no matching manifest layer"
            )

        mount_root = classify_root(layer)
        for repo in lock_layer.repos:
            steps.append(
                WorkspacePlanEntry(
                    mount_root=mount_root,
                    layer=lock_layer.name,
                    url=repo.url,
                    commit=repo.commit,
                    target_path=MOUNT_ROOTS[mount_root] / lock_layer.name / _repo_name(repo.url),
                )
            )

    return WorkspacePlan(steps=steps)


def plan_unlock(manifest: Manifest, layer_name: str, repo_url: str) -> UnlockPlan:
    """Compute the `source`/`dest`/`branch` promotion target for `unlock`.

    Pure, zero I/O: classifies `layer_name` against `manifest` to find its
    read-only mount root (mirroring `plan_projection`), then derives the
    `source` read-only checkout path, the `dest` writable worktree path
    under the reserved `worktrees` root, and a deterministic `branch` name.
    Raises `ProjectionError` naming the layer when it has no matching
    manifest layer — the adapter's `promote` is the one that later raises
    `AlreadyUnlockedError` if `dest` already exists.
    """
    manifest_layers_by_name: dict[str, CoreLayer | GitLayer | PublishedLayer] = {
        "core": manifest.core,
    }
    for layer in manifest.layers:
        manifest_layers_by_name[layer.name] = layer

    layer = manifest_layers_by_name.get(layer_name)
    if layer is None:
        raise ProjectionError(f"layer '{layer_name}' has no matching manifest layer")

    mount_root = classify_root(layer)
    repo_name = _repo_name(repo_url)
    return UnlockPlan(
        source=MOUNT_ROOTS[mount_root] / layer_name / repo_name,
        dest=MOUNT_ROOTS["worktrees"] / layer_name / repo_name,
        branch=f"unlock/{layer_name}/{repo_name}",
    )


def project_workspace(plan: WorkspacePlan, provider: "WorkspaceProvider") -> None:
    """Execute a `WorkspacePlan` by calling `provider.checkout` per entry.

    Pure orchestration only — depends solely on the `WorkspaceProvider`
    Protocol, never a concrete adapter, mirroring `build_lock`. Steps run in
    `plan.steps` order; a `checkout` failure propagates uncaught, stopping
    execution without touching subsequent steps.
    """
    for step in plan.steps:
        provider.checkout(step.url, step.commit, step.target_path)


def materialize_state(
    scanned: list[ScannedRepo],
    roots: Mapping[str, Path],
) -> MaterializedState:
    """Map raw `ScannedRepo` facts back into a `MaterializedState`. Pure, zero I/O.

    Derives each repo's layer name from the `/mnt/<root>/<layer>/...` path
    segment (matched against `roots`, e.g. `MOUNT_ROOTS`) and groups repos by
    layer. A repo scanned under the `worktrees` root always wins over a
    same-`url` entry from a read-only root for the same layer, since it
    represents that repo's current, promoted, writable state.

    Raises `ScanError` naming the offending path when a `ScannedRepo.path`
    does not match the `/mnt/<root>/<layer>/...` layout under any known root.
    """
    layers: dict[str, dict[str, MaterializedRepo]] = {}
    worktree_entries: list[tuple[str, ScannedRepo]] = []

    for repo in scanned:
        match = _match_root_and_layer(repo.path, roots)
        if match is None:
            raise ScanError(
                f"scanned path does not match the /mnt/<root>/<layer>/... layout: {repo.path}"
            )

        root_name, layer_name = match
        if root_name == "worktrees":
            worktree_entries.append((layer_name, repo))
            continue

        layers.setdefault(layer_name, {})[repo.url] = MaterializedRepo(
            url=repo.url, commit=repo.commit
        )

    # Applied last so a promoted worktree always overrides its read-only
    # counterpart, regardless of scan ordering.
    for layer_name, repo in worktree_entries:
        layers.setdefault(layer_name, {})[repo.url] = MaterializedRepo(
            url=repo.url, commit=repo.commit
        )

    return MaterializedState(
        layers=[
            MaterializedLayer(name=layer_name, repos=list(repos.values()))
            for layer_name, repos in layers.items()
        ]
    )


def _match_root_and_layer(path: Path, roots: Mapping[str, Path]) -> tuple[str, str] | None:
    """Match `path` against a known mount root and return `(root_name, layer)`.

    Returns `None` when `path` is not under any known root, or is under a
    root but missing the required `<layer>` path segment.
    """
    for root_name, base in roots.items():
        try:
            relative = path.relative_to(base)
        except ValueError:
            continue

        parts = relative.parts
        if len(parts) < 2:
            return None

        return root_name, parts[0]

    return None


def _repo_name(url: str) -> str:
    """Return the repo directory name derived from a git URL.

    Convention mirrors `composition._repo_name`: URL basename with any
    trailing slash and `.git` suffix removed.
    """
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


__all__ = [
    "MountRoot",
    "MOUNT_ROOTS",
    "ScannedRepo",
    "WorkspacePlanEntry",
    "WorkspacePlan",
    "UnlockPlan",
    "classify_root",
    "plan_projection",
    "plan_unlock",
    "project_workspace",
    "materialize_state",
]
