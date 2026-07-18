# Design: Harden catalog default validation against blank strings

## Technical Approach

Tighten the required-field invariant in
`src/odoo_forge/project_catalog/validation.py` so that the two **string**
defaults (`defaults.data_policy`, `defaults.target`) fail when they are `None`
*or* blank after `.strip()` (`""`, `"   "`). The typed reference fields
(`manifest_ref`, `source_context`) keep their unchanged `is None` check — they
are Pydantic models, not strings, so `.strip()` is inapplicable. No signatures,
no `InvalidCatalogRecord` shape, no `missing:field1+field2` reason-code format,
and no field ordering change. Maps directly to the proposal's "extend `is None`
to blank" approach.

## Architecture Decisions

### Decision: Introduce a `_is_blank` helper vs. inline predicate

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Module-level `_is_blank(value)` | One extra private symbol | **Chosen** |
| Inline `v is None or not v.strip()` (x3 sites) | Triplicated logic, drift risk | Rejected |

**Choice**: Add a private helper at the top of `validation.py`:

```python
def _is_blank(value: str | None) -> bool:
    """True when a required string output is absent or whitespace-only."""
    return value is None or not value.strip()
```

**Rationale**: The predicate is evaluated at three sites (two appends in
`invalid_required_fields`, plus the `validate_record` short-circuit). A single
source of truth guarantees the two code paths cannot disagree — the exact
concern the proposal raises — and reads as a named intent rather than a boolean
soup. `not value.strip()` covers both `""` and whitespace-only without a
separate length check.

### Decision: Keep typed refs on `is None`

**Choice**: `manifest_ref` / `source_context` checks are untouched.
**Alternatives considered**: Routing them through `_is_blank`.
**Rationale**: They are `ManifestRef | None` / `CatalogSourceContext | None`,
not strings; blank semantics do not apply and `_is_blank` is typed `str | None`.
Scope explicitly excludes them (proposal Out of Scope).

## Data Flow

Unchanged. Same call path, same return types:

    CatalogRecord ──→ validate_record ──→ ValidatedCatalogRecord
                           │  (short-circuit)
                           └──→ invalid_required_fields ──→ InvalidCatalogRecord

Only the boolean predicate for the two string defaults becomes stricter.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge/project_catalog/validation.py` | Modify | Add `_is_blank`; use it for `data_policy`/`target` in `invalid_required_fields` and the `validate_record` short-circuit |
| `tests/project_catalog/test_resolver.py` | Modify | Additive blank/whitespace cases only |

Concrete edits in `invalid_required_fields` (order/append sequence preserved):

```python
if _is_blank(record.defaults.data_policy):
    missing.append("data_policy_default")
if _is_blank(record.defaults.target):
    missing.append("target_default")
```

And in `validate_record` short-circuit:

```python
if manifest_ref is None or source_context is None \
   or _is_blank(data_policy) or _is_blank(target):
```

The `ValidatedCatalogRecord` construction is unchanged: once past the guard,
`data_policy`/`target` are non-blank `str`, satisfying the typed model.

## Interfaces / Contracts

No public contract change. `_is_blank` is private (`_` prefix, not exported in
`__all__`). `invalid_catalog_reason_code`, `invalid_required_fields`,
`validate_record` keep their exact signatures. A blank `data_policy` yields the
identical `missing:data_policy_default` classification a `None` would.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Blank/whitespace `data_policy` or `target` → `InvalidCatalogRecord` | Additive cases via existing `_resolve_incomplete(defaults=CatalogDefaults(...))` helper with `data_policy=""` / `target="   "` |
| Unit | Blank field classified identically to `None` (reason code + field) | Assert `invalid_fields`/`reason_code` equal the `None`-case output |
| Unit | Combined blank + `None` preserves fixed order | e.g. `manifest_ref=None` + blank `target` → `["manifest_ref", "target_default"]` |
| Regression | `_record()` (non-blank defaults) still validates | Existing green tests remain untouched |

Reuse the existing `_record()` fixture and `_resolve_incomplete` helper —
**no fixture edits**. New cases pass `CatalogDefaults` with blank values via
`update=`, exactly mirroring the current `None`/omitted-field tests, so no
existing assertion can regress.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary. Pure in-memory predicate.

## Migration / Rollout

No migration required. Revert the single `validation.py` edit (and added tests)
to restore `None`-only behavior.

## Blast Radius

Zero outside `validation.py` + `test_resolver.py`. `resolver.py`, `models.py`,
`interfaces.py` are untouched; `resolver` calls `validate_record` through its
unchanged signature and already handles `InvalidCatalogRecord`, so stricter
classification flows through existing control flow with no caller changes.

## Open Questions

- None.
