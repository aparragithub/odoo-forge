# Spec: Phase 2 Slice 2b — Resolution I/O (Git Adapter + Forge Lock)

## Purpose

Turn declared manifest intent into a pinned, reproducible `project.lock` by
resolving refs to real commit SHAs via a concrete git adapter, and writing
that lock through a `forge lock` CLI command. Adds the first I/O boundary
outside `odoo_forge` core. Builds on Slice 1 (`SourceProvider` port,
`Manifest`/`compose`) and Slice 2a (`resolve_default_ref`, canonical
`Lockfile` serialization).

Delivered as chained PRs: **PR-1** = adapter + `resolve_ref` + error taxonomy
+ 3rd import-linter contract. **PR-2** = lock-build use case + `forge lock`
CLI + `_load_lock` wiring to `from_json()`.

## Capability: ref-resolution (New) — PR-1

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

## Capability: forge-lock-cli (New) — PR-2

### Requirement: forge lock writes a pinned, canonical project.lock

`forge lock [--manifest project.yaml]` MUST parse and compose the manifest,
resolve `core.ref` via `resolve_default_ref` when unset, resolve every
declared layer/repo ref to a commit SHA through an injected
`SourceProvider`, build a `Lockfile` with `schema_version` set, and write it
via `to_canonical_json()`. All resolution/orchestration logic MUST live in
`odoo_forge` behind the `SourceProvider` Protocol; the CLI only constructs
the concrete adapter and orchestrates I/O.

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

## Capability: manifest (Modified)

### Requirement: SourceProvider is an interface with no implementation

`ports/source_provider.py` MUST define a `Protocol`/`ABC`; a concrete
adapter now exists (Slice 2b, outside `odoo_forge`) but `odoo_forge` core
MUST continue to depend only on the interface, never the concrete adapter.
(Previously: no adapter existed anywhere in the codebase.)

#### Scenario: import-linter enforces purity
- GIVEN the CI import-linter contracts forbidding `docker, boto3,
  kubernetes, git, typer, subprocess` in `odoo_forge`, forbidding
  `odoo_forge_cli`, and forbidding the Slice-2b adapter package, in
  `odoo_forge`
- WHEN CI runs
- THEN all contracts pass with zero violations

## Out of Scope

- Workspace projection / materialization / mount-roots / `unlock` (Slice 3).
- Docker/registry backend (Slice 4).
- Private-repo auth beyond surfacing a typed `AuthenticationError` (ambient
  git credentials only; no credential-passing in the port).
- Retry/backoff, response caching, offline mode, multi-remote resolution.
