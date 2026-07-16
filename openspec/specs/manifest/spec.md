# Spec: Phase 2 Manifest (Slice 1 + 2a — Pure Core & Resolution Prep)

## Purpose

Pure Pydantic v2 domain for `project.yaml`/`project.lock`, onion composition,
drift detection, and a thin `forge validate` CLI. Includes pure resolution helpers
and canonical lockfile serialization. No git/docker/network. (Slice 1 + 2a merged;
Slice 2b I/O deferred.)

## Capability: manifest-schema (New)

### Requirement: Core layer is a first-class field

`Manifest.core` MUST be a required `CoreLayer` with `type: Literal["core"]`,
`url: str = "https://github.com/odoo/odoo.git"`, `ref: str | None = None`. The
field itself MUST NOT duplicate `factory/versions.yaml`.

`core.ref: None` MUST be accepted as valid unresolved intent at the schema
level: a manifest with no explicit core ref is valid, and `compose()` MUST
preserve the `None` value unchanged — it MUST NOT resolve, mutate, or reject
it. Resolving `core.ref: None` to the `odoo_version` branch name (or any other
concrete ref) is OUT OF SCOPE for this pure manifest-core slice and belongs to
the future resolution/materialization slice, which will consume `Manifest`
alongside a `SourceProvider` adapter to produce concrete refs.

#### Scenario: Unresolved core ref is valid and untouched by composition
- GIVEN a manifest with `odoo_version: "19.0"` and no `core.ref`
- WHEN the manifest is parsed and then composed
- THEN parsing succeeds with `core.ref is None`
- AND composition succeeds without error
- AND the composed core layer's `ref` remains `None` (no resolution attempted)

#### Scenario: Overridden core url
- GIVEN a manifest with `core.url` set to a fork
- WHEN the manifest is parsed
- THEN the schema accepts the override and stores no resolved SHA (intent only)

### Requirement: Per-artifact edition gating

`GitRepo` and every `Layer` variant MUST expose an optional
`requires_edition: Literal["enterprise"] | None = None`. Coherence validation
MUST reject any `edition == "community"` manifest containing a repo or layer,
at any nesting depth, with `requires_edition == "enterprise"`.

#### Scenario: Enterprise repo nested in localization rejected
- GIVEN a community manifest whose `localization` `GitLayer` contains a repo
  `odoo-argentina-ee` with `requires_edition: "enterprise"`
- WHEN the manifest is composed
- THEN composition MUST raise a `CompositionError` naming the offending repo

#### Scenario: Enterprise manifest accepts the same repo
- GIVEN the same repo inside an `edition: "enterprise"` manifest
- WHEN the manifest is composed
- THEN composition succeeds

### Requirement: Explicit discriminated layer union

`Layer` MUST be `Annotated[PublishedLayer | GitLayer, Field(discriminator="type")]`,
each member carrying its own `type: Literal[...]` tag.

#### Scenario: Malformed layer yields a single-member error
- GIVEN a layer object missing required fields for both variants
- WHEN the manifest is parsed
- THEN validation MUST report exactly one error scoped to the tagged `type`,
  not ambiguous errors against both variants

### Requirement: Manifest hash is computed from the in-memory model

The manifest hash used as `Lockfile.generated_from` MUST be `sha256` over
`model_dump_json(exclude_none=False)` with sorted keys of the parsed `Manifest`
object. It MUST NOT read or hash raw file bytes.

#### Scenario: Semantically identical YAML, different formatting, same hash
- GIVEN two `project.yaml` files that parse to an equal `Manifest` but differ
  in whitespace/key order
- WHEN each is hashed
- THEN both hashes are identical

## Capability: onion-composition (New)

### Requirement: Published layers and Git overrides are effective

`PublishedLayer` MUST resolve to its declared version and immutable artifact digest; missing digest MUST fail before lock writing. PublishedLayer and Override remain supported. For an additional `GitLayer`, `Override.repo` MUST exactly equal the declared URL; replacement MUST precede resolution and the lock MUST record effective fork/ref/commit.

#### Scenario: Published and overridden entries are pinned
- GIVEN a published layer with version/digest and a matching Git override
- WHEN locking runs
- THEN the lock contains the published version/digest and effective fork/ref/commit

#### Scenario: Invalid declaration prevents lock writing
- GIVEN a missing digest or a duplicate, unknown, PublishedLayer, or core override target
- WHEN locking runs
- THEN it fails before writing a lock

### Requirement: Compose orders and validates without materializing

`compose(manifest) -> list[Layer]` MUST order core-first/client-last and validate edition coherence, override layers/repos, and final writable client. It MUST reject duplicates, unknown targets, invalid combinations, PublishedLayer/core targets before knowable I/O, and perform zero filesystem/network access.
(Previously: it did not validate override repositories, duplicates, or target combinations.)

#### Scenario: Override referencing a missing layer fails
- GIVEN an `Override` naming a layer not present in `manifest.layers`
- WHEN `compose()` runs
- THEN it raises `CompositionError` and performs no I/O

#### Scenario: odoo-idp fire test composes cleanly
- GIVEN a fixture manifest expressing odoo-idp (core odoo/odoo@19.0,
  enterprise layer, localization layer with ~17 ingadhoc repos including
  `odoo-argentina-ee` at `requires_edition: enterprise`, edition: enterprise)
- WHEN `compose()` runs
- THEN it returns an ordered layer chain with no errors

## Capability: drift-detection (New)

### Requirement: detect_drift is a pure three-input function

`detect_drift(manifest, lock, materialized)` MUST accept already-loaded
in-memory models, perform no disk reads, and return a `DriftReport` covering
manifest↔lock hash drift and lock↔state drift independently.

#### Scenario: Clean state
- GIVEN a lock whose `generated_from` matches the manifest hash and state
  matching lock-declared commits
- WHEN `detect_drift` runs
- THEN `DriftReport.is_clean` is `True`

#### Scenario: Manifest changed, lock stale
- GIVEN a lock hash that does not match the current manifest hash
- WHEN `detect_drift` runs
- THEN `manifest_lock_drift` is non-empty and `is_clean` is `False`

## Capability: forge-validate-cli (New)

### Requirement: forge validate delegates all logic to the core

`forge validate [--manifest project.yaml]` MUST parse and validate the manifest, run `compose()`, and report drift when a `project.lock` exists. When a workspace tree exists under the fixed mount roots, it MUST call `WorkspaceProvider.scan` for raw `ScannedRepo` facts, derive `MaterializedState` via the pure core `materialize_state`, and pass it into `detect_drift`. All decision logic MUST live in `odoo_forge`; the CLI only orchestrates and prints single-cause errors.

#### Scenario: malformed manifest reports a clear error
- GIVEN an invalid `project.yaml`
- WHEN `forge validate` runs
- THEN it exits non-zero with a single-cause, human-readable error

#### Scenario: malformed workspace evidence is rendered once
- GIVEN scan/projection materialization raises `ScanError`
- WHEN `forge validate` runs
- THEN the CLI emits one error message
- AND it does not re-raise or duplicate the boundary failure

#### Scenario: commit drift is reported from real workspace evidence
- GIVEN a lock and a workspace where one repo is checked out at a stale commit
- WHEN `forge validate` runs
- THEN it reports `commit_mismatch` drift for that repo

#### Scenario: unchanged lock and workspace remain clean
- GIVEN a lock whose `generated_from` matches the manifest hash and state matching lock-declared commits
- WHEN `forge validate` runs
- THEN `detect_drift` remains clean

## Capability: source-provider-port (New)

### Requirement: SourceProvider is an interface with no implementation

`ports/source_provider.py` MUST define a `Protocol`/`ABC` with no adapter in
this slice; `odoo_forge` MUST depend only on the interface.

#### Scenario: import-linter enforces purity
- GIVEN the CI import-linter contract forbidding `docker, boto3, kubernetes,
  git, typer, subprocess` in `odoo_forge`, and forbidding `odoo_forge_cli`
- WHEN CI runs
- THEN the contract passes with zero violations

## Capability: ref-resolution (New)

### Requirement: Default-ref substitution is a standalone pure helper

`resolve_default_ref(core: CoreLayer, odoo_version: str) -> str` MUST return
`odoo_version` when `core.ref is None`, and MUST return `core.ref` unchanged
when it is set. The helper MUST NOT mutate `core` or any `Manifest` instance,
and MUST perform zero I/O. It is a separate, opt-in function — not a change
to `compose()`.

#### Scenario: Unresolved ref defaults to odoo_version
- GIVEN a `CoreLayer` with `ref is None`
- WHEN `resolve_default_ref(core, "19.0")` is called
- THEN it returns `"19.0"`

#### Scenario: Explicit ref is preserved
- GIVEN a `CoreLayer` with `ref = "17.0-custom"`
- WHEN `resolve_default_ref(core, "19.0")` is called
- THEN it returns `"17.0-custom"` unchanged

#### Scenario: Helper does not mutate the model
- GIVEN a `CoreLayer` with `ref is None`
- WHEN `resolve_default_ref(core, "19.0")` is called
- THEN `core.ref` remains `None` after the call

#### Scenario: compose() regression — core.ref=None still untouched
- GIVEN a manifest with `odoo_version: "19.0"` and no `core.ref`
- WHEN the manifest is parsed and then composed (per the existing
  "Unresolved core ref is valid and untouched by composition" requirement)
- THEN the composed core layer's `ref` remains `None`
- AND `compose()` MUST NOT call `resolve_default_ref` internally

## Capability: lockfile-format (New)

### Requirement: project.lock has a canonical, versioned, deterministic serialization

`Lockfile` MUST expose pure canonical JSON helpers with integer `schema_version`, sorted keys, and fixed indentation; v2 represents published entries. Readers MUST accept v1/v2, reject unknown versions, and read v1 without fabricating published entries. Round-tripping MUST be byte-identical.
(Previously: only v1 and legacy-read behavior were defined.)

#### Scenario: schema_version is present
- GIVEN a `Lockfile` instance
- WHEN it is serialized
- THEN the JSON output contains a top-level integer `schema_version` field
  equal to the current schema version

#### Scenario: Key ordering is stable across runs
- GIVEN two structurally-equal `Lockfile` instances built in different field
  insertion order
- WHEN each is serialized
- THEN both outputs are byte-identical

#### Scenario: Round-trip is byte-stable
- GIVEN a `Lockfile` instance
- WHEN it is serialized, deserialized, and serialized again
- THEN the first and second serialized outputs are byte-identical

#### Scenario: Legacy document without schema_version is tolerated
- GIVEN a valid pre-Slice-2a lock without `schema_version`
- WHEN `from_json` is called
- THEN it succeeds as v1 and re-serialization emits `schema_version`

#### Scenario: Unknown version is rejected
- GIVEN an unsupported schema version
- WHEN `from_json` is called
- THEN it rejects the document

## Capability: ref-resolution (New) — Slice 2b

### Requirement: git adapter resolves refs to full commit SHAs

A concrete git `SourceProvider` adapter, living in a new package outside
`odoo_forge`, MUST implement `resolve_ref(url, ref) -> str` by querying the
remote (e.g. `git ls-remote`) and MUST return a full 40-character commit SHA
for both branches and tags. It MUST use argv-list subprocess invocation and
MUST NOT use `shell=True` or string interpolation into a shell command.

#### Scenario: Existing branch resolves to a SHA
- GIVEN a reachable remote and a ref that is an existing branch
- WHEN `resolve_ref(url, ref)` is called
- THEN it returns a 40-character commit SHA

#### Scenario: Existing tag resolves to a SHA
- GIVEN a reachable remote and a ref that is an existing tag
- WHEN `resolve_ref(url, ref)` is called
- THEN it returns a 40-character commit SHA

#### Scenario: Adapter satisfies the SourceProvider Protocol structurally
- GIVEN an instance of the concrete git adapter
- WHEN checked against `isinstance(adapter, SourceProvider)`
- THEN the check succeeds with no explicit inheritance from the port

### Requirement: Resolution failures surface as typed, actionable errors

The adapter MUST translate an empty/failed `git ls-remote` result into a
typed `RefNotFoundError`, a non-zero exit tied to auth into a typed
`AuthenticationError`, and an unreachable-network condition into a typed
`NetworkError`. It MUST NOT let a raw `subprocess`/`git` traceback
propagate to callers. Each error MUST carry the failing `url` and `ref` (or
host, for network failures) as actionable context.

#### Scenario: Ref not found fails loud with context
- GIVEN a reachable remote and a ref that does not exist on it
- WHEN `resolve_ref(url, ref)` is called
- THEN it raises `RefNotFoundError` naming the `url` and `ref`

#### Scenario: Unreachable remote raises a typed network error
- GIVEN a remote url that cannot be reached (DNS/connection failure)
- WHEN `resolve_ref(url, ref)` is called
- THEN it raises `NetworkError` naming the `url`, not a raw exception

#### Scenario: Auth failure raises a typed error
- GIVEN a private remote without valid ambient credentials
- WHEN `resolve_ref(url, ref)` is called
- THEN it raises `AuthenticationError` naming the `url`

### Requirement: Third import-linter contract guards the adapter package

A new import-linter contract MUST forbid `odoo_forge` (core) from importing
the git adapter package or any of `git`, `subprocess`. This is ADDED to the
existing two Slice-1 contracts — neither existing contract MUST be weakened.

#### Scenario: import-linter reports 3 kept, 0 broken
- GIVEN the updated `pyproject.toml` import-linter config
- WHEN CI runs `lint-imports`
- THEN all 3 contracts are kept and `odoo_forge` still imports zero
  `git`/`subprocess`/adapter-package symbols

## Capability: forge-lock-cli (New) — Slice 2b

### Requirement: forge lock writes a pinned, canonical project.lock

`forge lock [--manifest project.yaml]` MUST parse/compose, resolve core defaults and Git refs through `SourceProvider`, resolve PublishedLayer version/digest, apply overrides first, and write the canonical lock. Resolution MUST remain in `odoo_forge`; Git-only behavior and deterministic hashing/serialization MUST remain unchanged.
(Previously: it resolved core/Git refs only.)

#### Scenario: Valid manifest produces a pinned lock
- GIVEN a valid manifest with all refs resolvable
- WHEN `forge lock` runs
- THEN it writes `project.lock` containing a full commit SHA for every
  layer/repo and the current `schema_version`
- AND `forge validate` then reads it back successfully via `from_json()`

#### Scenario: Unresolved core.ref is resolved before pinning
- GIVEN a manifest with `core.ref: None` and `odoo_version: "19.0"`
- WHEN `forge lock` runs
- THEN the written lock pins the core layer to the SHA resolved from
  `"19.0"`, not a null/placeholder ref

#### Scenario: Resolution failure surfaces as a clean CLI error
- GIVEN a manifest referencing a ref that does not exist on its remote
- WHEN `forge lock` runs
- THEN it exits non-zero with a single-cause, human-readable error and no
  raw traceback, mirroring the `forge validate` resilient-boundary pattern
- AND no partial/corrupt `project.lock` is left on disk

## Capability: workspace-projection (New) — Slice 3

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

A pure `materialize_state(scanned: list[ScannedRepo], roots) -> MaterializedState` MUST derive each repo's layer name from `/mnt/<root>/<layer>/...` path evidence, group repos by layer, and perform zero I/O. It MUST raise `ScanError` for malformed or incoherent scan/projection evidence, and it MUST not invent mount placement or historical fallback. `MaterializedState` MUST remain identity/commit evidence only; path/root authority belongs to the separate planning view used by backend planning. Missing directories MAY materialize as partial evidence, and that partial state still remains identity/commit evidence only.

#### Scenario: fully projected tree materializes clean
- GIVEN `scan` returned one `ScannedRepo` per planned repo under its mount root
- WHEN `materialize_state(scanned, roots)` runs
- THEN the resulting `MaterializedState` preserves the lock's repo identities and commits
- AND `detect_drift(..., materialized=state)` reports `is_clean = True`

#### Scenario: missing directory is partial evidence, not a scan error
- GIVEN `scan` returned no entry for one planned layer's directory
- WHEN `materialize_state` runs
- THEN it completes without raising
- AND the returned state can still be used as partial identity/commit evidence

#### Scenario: missing directory still reports drift downstream
- GIVEN `materialize_state` returned partial evidence
- WHEN `detect_drift(..., materialized=state)` runs
- THEN the missing repo is reported as `not_materialized`

#### Scenario: malformed or incoherent scanned evidence fails loud
- GIVEN a `ScannedRepo` whose path does not match `/mnt/<root>/<layer>/...`
- WHEN `materialize_state` runs
- THEN it raises `ScanError` naming the offending path

#### Scenario: impossible root/layer pairing fails loud
- GIVEN scan evidence that names a root/layer combination that cannot exist
- WHEN `materialize_state` runs
- THEN it raises `ScanError` once

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

## Capability: forge-workspace-cli (New) — Slice 3

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

## Capability: manifest (Modified) — Slice 3

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
