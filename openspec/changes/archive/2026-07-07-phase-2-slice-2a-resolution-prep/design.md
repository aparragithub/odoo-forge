# Design: Phase 2 Slice 2a — Pure Resolution Prep

## Technical Approach

Two PURE, additive pieces on the existing `odoo_forge.manifest` domain, zero I/O,
no new deps, no adapter. (1) A default-ref substitution helper in a NEW
`resolution.py` module — the future git adapter (2b) will extend it. (2) A
formalized, versioned, byte-stable `project.lock` serialization contract as
methods on the `Lockfile` domain type. `compose()` stays byte-for-byte
behaviorally unchanged; the Slice 1 "compose preserves `core.ref=None`" scenario
stays green because the substitution helper is standalone and NEVER called from
`compose()`. Strict TDD, domain-first. Reconciles against spec `ref-resolution`
and `lockfile-format` requirements (running in parallel with sdd-spec).

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|----------|--------|----------|-----------
| Where `resolve_default_ref` lives | NEW module `src/odoo_forge/manifest/resolution.py` | (a) inline in `schema.py`; (b) seam inside `composition.py`; (c) method on `CoreLayer` | schema.py = data shapes only; composition.py would invite the reader (and future edits) to wire it into `compose()`, exactly the purity contract we must protect. A dedicated resolution module screams intent and is the natural home for 2b's impure SHA lookup (which will consume the `SourceProvider` port). A method on `CoreLayer` couples resolution policy to the schema and reads as "the model mutates itself". |
| Additivity proof | `compose()` file untouched; regression test asserts `compose(m)[0].ref is None` when `core.ref is None` | modify compose to substitute | keeps Slice 1 scenario green; substitution is opt-in, called only by the future lock use-case (2b) |
| Lock canonicalization | `json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"` on `Lockfile` | custom canonicalizer; compact `separators` | stdlib, no deps. `sort_keys=True` sorts DICT keys only — LIST order (semantically meaningful `layers`) is preserved. `indent=2` + trailing `\n` = diff/git-friendly (distinct purpose from the compact hash). |
| Version field | `schema_version: int = LOCKFILE_SCHEMA_VERSION` constant, starts at `1` | string semver; no field | integer is enough for a serialization contract; constant is the single source of truth |
| Slice-1-era locks (no field) | default fills `1` on `model_validate`; absence == v1, documented | reject / migrate | no released users; tolerant read, zero migration |

### Distinction from `compute_manifest_hash`
`compute_manifest_hash` (unchanged) hashes the **Manifest** with COMPACT
separators for a stable digest. `Lockfile.to_canonical_json` serializes the
**Lockfile** with INDENT for a readable, diffable on-disk file. Different inputs,
different purposes — do not unify them.

## Data Flow

    (2b use-case) core.ref=None → resolve_default_ref(core, odoo_version) → branch str
    Lockfile → to_canonical_json() → bytes (sorted keys, indent, \n)   [WRITE, wired in 2b]
    raw → Lockfile.from_json() → Lockfile.model_validate → Lockfile     [READ, CLI _load_lock later]
    compose(manifest) ── UNCHANGED, never calls resolve_default_ref ──> chain (core.ref stays None)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge/manifest/resolution.py` | Create | pure `resolve_default_ref(core, odoo_version) -> str` |
| `src/odoo_forge/manifest/lockfile.py` | Modify | add `LOCKFILE_SCHEMA_VERSION=1`, `Lockfile.schema_version`, `to_canonical_json()`, `from_json()` |
| `src/odoo_forge/manifest/composition.py` | Untouched | proves additivity |
| `src/odoo_forge_cli/main.py` | Untouched (2a) | `_load_lock` may adopt `from_json` in 2b when the writer lands |
| `openspec/specs/manifest/spec.md` | Modify (sdd-spec) | `lockfile-format` + `ref-resolution` requirements |
| `tests/manifest/test_resolution.py` | Create | default-ref cases + compose-preserves-None regression |
| `tests/manifest/test_lockfile_format.py` | Create | byte-stable round-trip + schema_version + missing-field tolerance |

## Interfaces / Contracts

```python
# src/odoo_forge/manifest/resolution.py
from odoo_forge.manifest.schema import CoreLayer

def resolve_default_ref(core: CoreLayer, odoo_version: str) -> str:
    """Pure: None -> odoo_version branch; explicit ref echoed unchanged."""
    return core.ref if core.ref is not None else odoo_version
```

```python
# src/odoo_forge/manifest/lockfile.py (additive)
LOCKFILE_SCHEMA_VERSION = 1

class Lockfile(BaseModel):
    schema_version: int = LOCKFILE_SCHEMA_VERSION
    generated_from: str
    layers: list[ResolvedLayer] = []

    def to_canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"

    @classmethod
    def from_json(cls, raw: str) -> "Lockfile":
        return cls.model_validate(json.loads(raw))
```

## import-linter

No new adapter and `resolution.py` imports only `schema`. No new contract; gate
stays **2 kept / 0 broken**. The existing "core-is-pure" forbidden contract already
guards resolution.py against accidental git/subprocess imports in 2b.

## Drift-detection implication (flagged)

`detect_drift` consumes the PARSED `Lockfile` model, not bytes, and
`compute_manifest_hash` hashes the **Manifest**, not the Lockfile — so lock
serialization format changes are drift-neutral BY CONSTRUCTION. The only guard:
adding `schema_version` (defaulted) must not alter `generated_from`. Regression
test: a Slice-1-era lock dict (no `schema_version`) validates and yields an
identical `DriftReport` to today. No migration required.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------
| Unit — resolution | `None -> odoo_version`; explicit ref echoed; `compose(m)[0].ref` stays `None` (regression) | in-memory `CoreLayer`/`Manifest` |
| Unit — lockfile-format | serialize→deserialize→serialize byte-identical; keys sorted, `layers` order preserved; `schema_version` emitted =1; trailing `\n` | round-trip on `Lockfile` |
| Unit — back-compat | dict without `schema_version` validates to v1; `detect_drift` result unchanged | `model_validate` + `detect_drift` |
| Arch gate | core stays pure | import-linter (2 kept / 0 broken) |

## Migration / Rollout

No migration. Pure additive change in `src/odoo_forge/manifest/`; revert the
branch to roll back. Diff well under the 400-line review budget; single PR,
`review-readability` sufficient.

## Open Questions

- None blocking. Wiring `_load_lock`→`from_json` and the `forge lock` writer are
  explicitly deferred to Slice 2b.
