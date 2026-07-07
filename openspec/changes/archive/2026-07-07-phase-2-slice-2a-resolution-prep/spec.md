# Delta Spec: Phase 2 Slice 2a — Pure Resolution Prep

Amends `openspec/specs/manifest/spec.md` (Phase 2 Slice 1 — Manifest Core).
Pure, additive only. No network, subprocess, or new runtime deps.

## Out of Scope

- Concrete git `SourceProvider` adapter, `resolve_ref` SHA lookup, `git ls-remote`.
- `forge lock` CLI command (composition root that writes the lock).
- Error taxonomy for ref-not-found / auth-failure.
- New adapter package or third import-linter contract (stays 2 kept / 0 broken).

## ADDED Requirements

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

### Requirement: `project.lock` has a canonical, versioned, deterministic serialization

`Lockfile` MUST expose pure `to_canonical_json() -> str` and `from_json(data: str) -> Lockfile` helpers. The JSON payload MUST include an explicit integer
`schema_version` field (starting at `1`), MUST use sorted keys, and MUST use a
fixed indentation. Serializing, deserializing, and re-serializing the same
`Lockfile` MUST produce byte-identical output both times.

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
