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

### Requirement: Compose orders and validates without materializing

`compose(manifest) -> list[Layer]` MUST order layers core-first,
client-last, and MUST validate: edition coherence (above), every
`Override.layer` reference exists in `layers`, and the client is the final
writable layer. It MUST perform zero filesystem or network access.

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

`forge validate [--manifest project.yaml]` MUST parse and validate the
manifest, run `compose()`, and report drift when a `project.lock` exists. All
decision logic MUST live in `odoo_forge`; the CLI only orchestrates and
prints.

#### Scenario: Malformed manifest reports a clear error
- GIVEN an invalid `project.yaml`
- WHEN `forge validate` runs
- THEN it exits non-zero with a single-cause, human-readable error

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

`Lockfile` MUST expose pure `to_canonical_json() -> str` and `from_json(data: str) -> Lockfile`
helpers. The JSON payload MUST include an explicit integer `schema_version` field
(starting at `1`), MUST use sorted keys, and MUST use a fixed indentation.
Serializing, deserializing, and re-serializing the same `Lockfile` MUST produce
byte-identical output both times.

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
- GIVEN a JSON document with no `schema_version` field (pre-Slice-2a lock
  shape) but otherwise valid `Lockfile` fields
- WHEN `from_json` is called
- THEN it MUST succeed, treating the absent field as schema version `1`
- AND re-serializing the result MUST emit the current `schema_version`
  explicitly

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
