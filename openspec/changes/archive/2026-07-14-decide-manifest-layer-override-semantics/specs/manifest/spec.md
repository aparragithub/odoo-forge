# Delta for manifest

## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: project.lock has a canonical, versioned, deterministic serialization

`Lockfile` MUST expose pure canonical JSON helpers with integer `schema_version`, sorted keys, and fixed indentation; v2 represents published entries. Readers MUST accept v1/v2, reject unknown versions, and read v1 without fabricating published entries. Round-tripping MUST be byte-identical.
(Previously: only v1 and legacy-read behavior were defined.)

#### Scenario: schema_version is present
- GIVEN a `Lockfile` instance
- WHEN it is serialized
- THEN JSON contains integer `schema_version` equal to the current version

#### Scenario: Key ordering is stable across runs
- GIVEN two equal lockfiles with different insertion order
- WHEN each is serialized
- THEN outputs are byte-identical

#### Scenario: Round-trip is byte-stable
- GIVEN a `Lockfile` instance
- WHEN serialized, deserialized, and serialized again
- THEN both outputs are byte-identical

#### Scenario: Legacy document without schema_version is tolerated
- GIVEN a valid pre-Slice-2a lock without `schema_version`
- WHEN `from_json` is called
- THEN it succeeds as v1 and re-serialization emits `schema_version`

#### Scenario: Unknown version is rejected
- GIVEN an unsupported schema version
- WHEN `from_json` is called
- THEN it rejects the document

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
