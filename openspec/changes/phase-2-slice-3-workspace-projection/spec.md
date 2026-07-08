# Spec: Phase 2 Slice 3 — Workspace Projection

## Purpose

Turn a pinned `project.lock` into real checkouts under fixed `/mnt/*` mount
roots, scan that tree back into a real `MaterializedState`, and let a
developer promote a read-only checkout to a writable working copy
(`unlock`). Mirrors the Slice 2b hexagonal split: pure core, new port, new
sibling adapter package, additive purity contract.

## Capability: workspace-projection (New)

### Requirement: Layer category classifies the projection mount root

Each `GitLayer`/`PublishedLayer` MUST expose an additive, optional
`category: Literal["custom","community","localization","enterprise"] | None = None`
field (back-compat: absent on all Slice 1/2a/2b fixtures). A pure
`classify_root(layer) -> MountRoot` MUST return: `"enterprise"` when
`requires_edition == "enterprise"`; else the explicit `category` when set; else
`"custom"` as the default. `CoreLayer` MUST always classify to `"community"`.
`classify_root` MUST NEVER return `"worktrees"` — that root is reserved
exclusively for `unlock`-promoted writable copies.

#### Scenario: Legacy layer without category falls back to custom
- GIVEN a `GitLayer` with no `category` and `requires_edition` unset
- WHEN `classify_root(layer)` runs
- THEN it returns `"custom"`

#### Scenario: Enterprise repo forces enterprise root regardless of category
- GIVEN a layer with `category="localization"` and `requires_edition="enterprise"`
- WHEN `classify_root(layer)` runs
- THEN it returns `"enterprise"`

#### Scenario: Core always classifies to community
- GIVEN the manifest's `core: CoreLayer`
- WHEN `classify_root(core)` runs
- THEN it returns `"community"`

### Requirement: plan_projection is a pure, deterministic use-case

`plan_projection(manifest: Manifest, lock: Lockfile) -> WorkspacePlan` MUST
join `lock.layers` to `manifest` layers by name, classify each to a mount
root, and emit one deterministic `ProjectionStep` per resolved repo
(`mount_root`, `layer`, `url`, `commit`, target path), preserving
`lock.layers` order. It MUST perform zero I/O and MUST raise a typed
`ProjectionError` when a locked layer has no matching manifest layer.

#### Scenario: Plan mirrors lock order
- GIVEN a lock with layers `[core, enterprise, custom-x]`
- WHEN `plan_projection` runs
- THEN `WorkspacePlan.steps` preserves that order, one step per repo

#### Scenario: Orphaned lock layer fails loud
- GIVEN a lock layer name absent from the current manifest
- WHEN `plan_projection` runs
- THEN it raises `ProjectionError` naming the orphaned layer, with no partial plan returned

### Requirement: WorkspaceProvider port defines checkout, scan, and promote

`ports/workspace_provider.py` MUST define a `Protocol` with
`checkout(url: str, commit: str, dest: Path) -> None`,
`scan(roots: Sequence[Path]) -> list[ScannedRepo]`, and
`promote(source: Path, dest: Path, branch: str) -> None`. The adapter MUST
stay dumb: `scan` returns raw `ScannedRepo{path, url, commit}` facts read
straight off disk (no layer/mount-root knowledge), and `promote` only
performs the side-effecting worktree move to a `dest` path and `branch` name
that the pure core already decided — the adapter never derives paths or
branch names itself. `odoo_forge` MUST depend only on this interface; no
adapter lives in core.

#### Scenario: import-linter enforces purity
- GIVEN the 4-contract import-linter config
- WHEN CI runs `lint-imports`
- THEN `odoo_forge` imports zero `git`/filesystem-write symbols and never
  imports the adapter package

### Requirement: materialize_state is a pure core function over raw scan results

A pure `materialize_state(scanned: list[ScannedRepo], roots) -> MaterializedState`
MUST live in `odoo_forge` (not the adapter) and derive each repo's layer name
from its `/mnt/<root>/<layer>/...` path segment, grouping by layer into
`MaterializedLayer` entries. It MUST perform zero I/O — all disk reads
already happened in the adapter's `scan`. `ScannedRepo` entries whose path
does not match the `/mnt/<root>/<layer>/...` layout MUST raise a typed
`ScanError` naming the offending path.

#### Scenario: Fully projected tree materializes clean
- GIVEN `scan` returned one `ScannedRepo` per planned repo under its mount root
- WHEN `materialize_state(scanned, roots)` runs
- THEN the resulting `MaterializedState` matches the lock 1:1 and
  `detect_drift(..., materialized=state)` reports `is_clean = True`

#### Scenario: Missing directory is not an error
- GIVEN `scan` returned no entry for one planned layer's directory
- WHEN `materialize_state` runs
- THEN it completes without raising; `detect_drift` reports `not_materialized` for it

#### Scenario: Malformed scanned path fails loud
- GIVEN a `ScannedRepo` whose path does not match `/mnt/<root>/<layer>/...`
- WHEN `materialize_state` runs
- THEN it raises `ScanError` naming the offending path

### Requirement: unlock promotes one repo to a writable working state

`unlock(layer, repo_url)` MUST target exactly one materialized repo
(repo-level granularity). The pure core MUST compute the `source`, `dest`
(`/mnt/worktrees/<layer>/<repo>`), and `branch` for the promotion and pass
them to `WorkspaceProvider.promote(source, dest, branch)`; the adapter only
executes the worktree move. The command MUST leave the repo writable and
immediately usable for local commits, MUST keep the originally-locked commit
recoverable, and MUST raise a typed `AlreadyUnlockedError` if the target
`dest` already exists as a writable copy.

#### Scenario: Read-only checkout is promoted
- GIVEN a repo checked out read-only at its locked commit
- WHEN `unlock(layer, repo_url)` runs
- THEN `promote(source, dest, branch)` is called with a core-computed `dest`
  under `/mnt/worktrees/<layer>/`, the repo becomes writable, and the locked
  commit remains recoverable

#### Scenario: Re-unlocking fails loud
- GIVEN a repo already promoted to writable at its computed `dest`
- WHEN `unlock` runs again on it
- THEN it raises `AlreadyUnlockedError` naming the layer/repo, without
  calling `promote` again

## Capability: forge-workspace-cli (New)

### Requirement: forge project executes the plan through a resilient boundary

`forge project [--manifest][--lock]` MUST load the manifest and lock, call
`plan_projection`, then execute each step via the injected
`WorkspaceProvider.checkout`. Each individual checkout MUST be atomic (no
half-cloned directory left on failure — clone-to-temp then rename). On a
step failure the command MUST stop, MUST NOT touch already-completed steps,
and MUST exit non-zero with a single-cause, human-readable error (no raw
traceback).

#### Scenario: Valid lock projects every layer
- GIVEN a valid `project.lock`
- WHEN `forge project` runs
- THEN every locked repo is checked out under its classified mount root

#### Scenario: Mid-plan checkout failure stops cleanly
- GIVEN a plan where the third step's remote is unreachable
- WHEN `forge project` runs
- THEN steps 1–2 remain checked out, step 3 leaves no half-cloned directory,
  and the command exits non-zero naming the failing repo

### Requirement: forge unlock promotes a targeted repo

`forge unlock --layer NAME --repo URL` MUST call `unlock`, which computes
`source`/`dest`/`branch` in the pure core and invokes
`WorkspaceProvider.promote(source, dest, branch)`, then report the
core-computed branch name, or exit non-zero on
`AlreadyUnlockedError`/`ScanError` with a single-cause message.

#### Scenario: Unlock succeeds and reports the branch
- GIVEN a read-only materialized repo
- WHEN `forge unlock --layer core --repo <url>` runs
- THEN `promote` is called with the core-computed `dest`/`branch`, and the
  command exits zero and prints that branch name

## Capability: manifest (Modified)

### Requirement: forge validate delegates all logic to the core

`forge validate [--manifest project.yaml]` MUST parse and validate the
manifest, run `compose()`, and report drift when a `project.lock` exists.
When a workspace tree exists under the fixed mount roots, it MUST call
`WorkspaceProvider.scan` for raw `ScannedRepo` facts, derive the real
`MaterializedState` via the pure core `materialize_state`, and pass it into
`detect_drift` instead of `None`. All decision logic MUST live in
`odoo_forge`; the CLI only orchestrates and prints.
(Previously: `forge validate` always passed `materialized=None`, never
activating the lock↔state drift path.)

#### Scenario: Malformed manifest reports a clear error
- GIVEN an invalid `project.yaml`
- WHEN `forge validate` runs
- THEN it exits non-zero with a single-cause, human-readable error

#### Scenario: Drift detected against a real workspace
- GIVEN a lock and a workspace where one repo is checked out at a stale commit
- WHEN `forge validate` runs
- THEN it reports `commit_mismatch` drift for that repo, sourced from a real scan

## Out of Scope

- Override application (fork url/ref substitution) — re-deferred.
- Docker/local-backend mount execution — Slice 4.
- Retry/backoff/observability on checkout — deferred.
- Generic `/mnt/{name}` mapping — rejected; fixed 5-root table only.
