"""Pure workspace projection planning: manifest + lock -> filesystem plan.

`classify_root` and `plan_projection` are the pure, provider-free half of
the Slice 3 projection pipeline. The lock already carries resolved commits
(pinned by `build_lock`), so no `SourceProvider`/`WorkspaceProvider` I/O is
needed here — this module performs zero I/O and never raises anything
except the typed `ProjectionError`.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from odoo_forge.manifest.composition import compose
from odoo_forge.manifest.drift import detect_drift
from odoo_forge.manifest.errors import MountPlanningError, ProjectionError, ScanError
from odoo_forge.manifest.lockfile import Lockfile
from odoo_forge.manifest.resolution import resolve_default_ref
from odoo_forge.manifest.schema import (
    CoreLayer,
    EnterpriseLayer,
    GitLayer,
    Manifest,
    PublishedLayer,
)
from odoo_forge.manifest.state import MaterializedLayer, MaterializedRepo, MaterializedState

if TYPE_CHECKING:
    from odoo_forge.ports.workspace_provider import WorkspaceProvider

# Fixed 5-root table. `worktrees` is reserved exclusively for `unlock`-promoted
# writable copies and is NEVER returned by `classify_root` — read-only
# projection only ever targets the other 4 roots.
MountRoot = Literal["custom", "community", "localization", "enterprise"]

# Fixed: container FS convention. `plan_backend` derives the mount root name
# from `evidence.container_path.parts[2]` (`backend/plan.py:86`), so the
# CONTAINER base must never vary with the HOST base — only the HOST base is
# configurable (resolved at the CLI composition root, `odoo_forge_cli.main`).
CONTAINER_MOUNT_BASE: Path = Path("/mnt")


def build_mount_roots(base: Path) -> dict[str, Path]:
    """Build the fixed 5-root table rooted at `base`. Pure, zero I/O."""
    return {
        "community": base / "community",
        "custom": base / "custom",
        "localization": base / "localization",
        "enterprise": base / "enterprise",
        "worktrees": base / "worktrees",
    }


MOUNT_ROOTS: dict[str, Path] = build_mount_roots(CONTAINER_MOUNT_BASE)


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


class MountEvidence(BaseModel):
    layer: str
    url: str
    source_path: Path
    container_path: Path
    read_only: bool


class MountPlanningView(BaseModel):
    mounts: tuple[MountEvidence, ...]


class UnlockPlan(BaseModel):
    """Core-computed promotion target for `unlock`. Pure, zero I/O."""

    source: Path
    dest: Path
    branch: str


def classify_root(layer: CoreLayer | EnterpriseLayer | GitLayer | PublishedLayer) -> MountRoot:
    """Map a layer to its read-only projection mount root. Pure, zero I/O.

    Precedence: `CoreLayer` always classifies to `"community"`; the
    `EnterpriseLayer` singleton always classifies to `"enterprise"`; else the
    layer's explicit `category` when set; else `"custom"` as the default.
    `requires_enterprise` is a coherence precondition only and never affects
    mount classification. Never returns `"worktrees"`.
    """
    if isinstance(layer, CoreLayer):
        return "community"
    if isinstance(layer, EnterpriseLayer):
        return "enterprise"
    if layer.category is not None:
        return layer.category
    return "custom"


def plan_projection(
    manifest: Manifest, lock: Lockfile, roots: Mapping[str, Path] = MOUNT_ROOTS
) -> WorkspacePlan:
    """Join v2 `lock.git_layers` to the current manifest by name and classify each
    to a mount root, preserving Git-layer order. Published entries are retained
    in the lock but have no Git checkout. Pure, zero I/O; `roots` is injectable,
    defaulting to the fixed container table.

    Raises `ProjectionError` naming the orphaned layer when a locked layer
    has no matching manifest layer — no partial plan is ever returned.
    """
    manifest_layers_by_name: dict[str, CoreLayer | GitLayer | PublishedLayer] = {
        "core": manifest.core,
    }
    for layer in manifest.layers:
        manifest_layers_by_name[layer.name] = layer

    steps: list[WorkspacePlanEntry] = []
    for lock_layer in lock.git_layers:
        matched_layer = manifest_layers_by_name.get(lock_layer.name)
        if matched_layer is None:
            raise ProjectionError(
                f"locked layer '{lock_layer.name}' has no matching manifest layer"
            )

        mount_root = classify_root(matched_layer)
        for repo in lock_layer.repos:
            steps.append(
                WorkspacePlanEntry(
                    mount_root=mount_root,
                    layer=lock_layer.name,
                    url=repo.url,
                    commit=repo.commit,
                    target_path=roots[mount_root] / lock_layer.name / _repo_name(repo.url),
                )
            )

    return WorkspacePlan(steps=steps)


def plan_unlock(
    manifest: Manifest, layer_name: str, repo_url: str, roots: Mapping[str, Path] = MOUNT_ROOTS
) -> UnlockPlan:
    """Compute the `source`/`dest`/`branch` promotion target for `unlock`.

    Pure, zero I/O; `roots` is injectable, defaulting to the fixed container
    table. Classifies `layer_name` against `manifest` to find its read-only
    mount root (mirroring `plan_projection`), then derives the `source`
    read-only checkout path, the `dest` writable worktree path under the
    reserved `worktrees` root, and a deterministic `branch` name. Raises
    `ProjectionError` when the layer is unknown or the repository URL is not
    declared by that layer. The adapter's `promote` is the one that later
    raises `AlreadyUnlockedError` if `dest` already exists.
    """
    manifest_layers_by_name: dict[str, CoreLayer | GitLayer | PublishedLayer] = {
        "core": manifest.core,
    }
    for layer in manifest.layers:
        manifest_layers_by_name[layer.name] = layer

    matched_layer = manifest_layers_by_name.get(layer_name)
    if matched_layer is None:
        raise ProjectionError(f"layer '{layer_name}' has no matching manifest layer")

    declared_urls = (
        [matched_layer.url]
        if isinstance(matched_layer, CoreLayer)
        else [repo.url for repo in matched_layer.repos]
        if isinstance(matched_layer, GitLayer)
        else []
    )
    if repo_url not in declared_urls:
        raise ProjectionError(f"repo does not belong to layer '{layer_name}'")

    mount_root = classify_root(matched_layer)
    effective_url = next(
        (
            override.fork
            for override in manifest.overrides
            if override.layer == layer_name and override.repo == repo_url
        ),
        repo_url,
    )
    repo_name = _repo_name(effective_url)
    return UnlockPlan(
        source=roots[mount_root] / layer_name / repo_name,
        dest=roots["worktrees"] / layer_name / repo_name,
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


def build_mount_planning_view(
    manifest: Manifest,
    lock: Lockfile | None,
    scanned: Sequence[ScannedRepo],
    state: MaterializedState,
    roots: Mapping[str, Path],
    container_roots: Mapping[str, Path] = MOUNT_ROOTS,
) -> MountPlanningView:
    """Validate scan facts and select one authoritative bind per locked repository.

    `roots` is the HOST table (used for scan matching, dedup, and
    `source_path`). `container_roots` is the CONTAINER table (used ONLY for
    `MountEvidence.container_path`), defaulting to the fixed `/mnt` table so
    the container side never varies with a custom host base.
    """
    if lock is None:
        raise MountPlanningError("mount planning requires a project lock")
    if detect_drift(manifest, lock, None).manifest_lock_drift:
        raise MountPlanningError("manifest/lock drift")
    _validate_lock_structure(manifest, lock)

    plan = plan_projection(manifest, lock)
    expected = {(step.layer, step.url): step for step in plan.steps}
    if len(expected) != len(plan.steps):
        raise MountPlanningError("lock contains duplicate repository identities")
    container_paths = [
        container_roots[step.mount_root] / step.layer / _repo_name(step.url) for step in plan.steps
    ]
    if len(set(container_paths)) != len(container_paths):
        raise MountPlanningError("lock contains conflicting projected container paths")
    sources: dict[tuple[str, str], dict[str, ScannedRepo]] = {}

    for repo in scanned:
        match = _match_root_and_layer(repo.path, roots)
        if match is None:
            raise ScanError(
                f"scanned path does not match the /mnt/<root>/<layer>/... layout: {repo.path}"
            )

        root_name, layer = match
        identity = (layer, repo.url)
        step = expected.get(identity)
        if step is None:
            raise MountPlanningError(
                f"unexpected scanned evidence for '{layer}' / '{_repo_name(repo.url)}'"
            )
        source_kind = "worktree" if root_name == "worktrees" else "read_only"
        expected_path = (
            roots["worktrees"] / layer / _repo_name(repo.url)
            if source_kind == "worktree"
            else roots[step.mount_root] / layer / _repo_name(repo.url)
        )
        if repo.path != expected_path:
            raise MountPlanningError(f"incoherent path for '{layer}' / '{_repo_name(repo.url)}'")

        by_source = sources.setdefault(identity, {})
        if source_kind in by_source:
            raise MountPlanningError(
                f"duplicate {source_kind} evidence for '{layer}' / '{_repo_name(repo.url)}'"
            )
        by_source[source_kind] = repo

    for identity, by_source in sources.items():
        selected = by_source.get("worktree") or by_source["read_only"]
        step = expected[identity]
        if selected.commit != step.commit:
            raise MountPlanningError(f"commit drift for '{step.layer}' / '{_repo_name(step.url)}'")

    mounts: list[MountEvidence] = []
    for identity, step in sorted(expected.items()):
        by_source = sources.get(identity, {})
        evidence = by_source.get("worktree") or by_source.get("read_only")
        if evidence is None:
            raise MountPlanningError(
                f"missing required evidence for '{step.layer}' / '{_repo_name(step.url)}'"
            )

        mounts.append(
            MountEvidence(
                layer=step.layer,
                url=step.url,
                source_path=evidence.path,
                container_path=container_roots[step.mount_root] / step.layer / _repo_name(step.url),
                read_only="worktree" not in by_source,
            )
        )

    _validate_materialized_state(
        state, {identity: step.commit for identity, step in expected.items()}
    )
    return MountPlanningView(mounts=tuple(mounts))


def _validate_lock_structure(manifest: Manifest, lock: Lockfile) -> None:
    compose(manifest)
    overrides = {(item.layer, item.repo): item for item in manifest.overrides}
    expected_git: list[tuple[str, tuple[tuple[str, str], ...]]] = [
        ("core", ((manifest.core.url, resolve_default_ref(manifest.core, manifest.odoo_version)),))
    ]
    expected_published: list[tuple[str, str, str]] = []
    for layer in manifest.layers:
        if isinstance(layer, GitLayer):
            repos = []
            for repo in layer.repos:
                override = overrides.get((layer.name, repo.url))
                repos.append((override.fork, override.ref) if override else (repo.url, repo.ref))
            expected_git.append((layer.name, tuple(repos)))
        else:
            expected_published.append((layer.name, layer.source, layer.version))

    actual_git = [
        (layer.name, tuple((repo.url, repo.ref) for repo in layer.repos))
        for layer in lock.git_layers
    ]
    actual_published = [
        (layer.name, layer.source, layer.version) for layer in lock.published_layers
    ]
    if expected_git != actual_git or expected_published != actual_published:
        raise MountPlanningError("manifest/lock structural mismatch")


def _validate_materialized_state(
    state: MaterializedState, expected: Mapping[tuple[str, str], str]
) -> None:
    actual: dict[tuple[str, str], str] = {}
    for layer in state.layers:
        for repo in layer.repos:
            identity = (layer.name, repo.url)
            if identity in actual:
                raise MountPlanningError(
                    f"duplicate materialized evidence for '{layer.name}' / '{_repo_name(repo.url)}'"
                )
            actual[identity] = repo.commit

    if set(actual) != set(expected):
        raise MountPlanningError("materialized evidence does not match required mount evidence")
    for identity, expected_commit in expected.items():
        if actual[identity] != expected_commit:
            raise MountPlanningError(
                f"materialized commit drift for '{identity[0]}' / '{_repo_name(identity[1])}'"
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
    """Return a credential-safe repository identity derived from a git URL.

    Prefer the path basename, then a URL hostname, without exposing URL metadata.
    """
    clean_url = url.split("#", 1)[0].split("?", 1)[0]
    try:
        parsed = urlsplit(clean_url)
        if parsed.path.strip("/"):
            candidate = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        elif parsed.hostname:
            candidate = parsed.hostname
        else:
            candidate = clean_url.rstrip("/").rsplit("/", 1)[-1]
            candidate = candidate.rsplit(":", 1)[-1].rsplit("@", 1)[-1]
    except ValueError:
        candidate = "repository"
    return candidate.removesuffix(".git") or "repository"


__all__ = [
    "MountRoot",
    "CONTAINER_MOUNT_BASE",
    "MOUNT_ROOTS",
    "build_mount_roots",
    "ScannedRepo",
    "WorkspacePlanEntry",
    "WorkspacePlan",
    "MountEvidence",
    "MountPlanningView",
    "UnlockPlan",
    "classify_root",
    "plan_projection",
    "plan_unlock",
    "project_workspace",
    "materialize_state",
    "build_mount_planning_view",
]
