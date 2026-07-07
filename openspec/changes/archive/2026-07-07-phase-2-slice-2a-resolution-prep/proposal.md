# Proposal: Phase 2 Slice 2a — Pure Resolution Prep

## Intent

Slice 2 (Resolution) was split into 2a (pure) + 2b (I/O) to protect the 400-line
review budget and keep pure logic out of the same diff as subprocess/network risk
(decision obs 2301). This is 2a: the two PURE, low-risk pieces the impure git
adapter (2b) will later consume. No network, no subprocess, no new runtime deps.
It closes Slice 1 verify gap W3 (lock format never formalized) and adds the
default-ref substitution seam without touching the `compose()` purity contract.

## Scope

### In Scope
- **Default-ref substitution helper** — a NEW pure function (e.g. `resolve_default_ref(core, odoo_version) -> str`) mapping `core.ref: None → odoo_version` branch name. Pure string logic, zero I/O, stays inside `odoo_forge` core.
- **Formalized `project.lock` serialization contract** — JSON with an explicit `schema_version` field, deterministic stable key ordering, and fixed indentation, plus pure (de)serialize helpers on the `Lockfile` domain type (replacing the CLI's ad hoc `Lockfile.model_dump(mode="json")`).
- Spec amendments for both, reconciled against the Slice 1 "preserve untouched" rule (see key design question).

### Out of Scope (belongs to Slice 2b)
- Concrete git `SourceProvider` adapter, `resolve_ref` SHA lookup, `git ls-remote`, any network/subprocess I/O.
- `forge lock` CLI command (the composition root that WRITES the lock).
- Error taxonomy for ref-not-found / auth-failure.
- New adapter package + third import-linter contract (2a adds NO adapter; gate stays **2 kept / 0 broken**).

## Key design question (flag for sdd-design; do NOT lock the mechanism here)
Slice 1 spec mandates `compose()` MUST preserve `core.ref=None` unchanged. Intent:
default-substitution is a SEPARATE opt-in pure helper called by the future lock
use-case — NOT a change to `compose()`. Design must decide precisely where it lives
(standalone resolver vs. use-case seam) so the "compose preserves None" scenario stays
green while the new helper is additive.

## Capabilities

### New Capabilities
- `lockfile-format`: versioned, canonical, deterministic `project.lock` JSON serialization + pure (de)serialize helpers.
- `ref-resolution`: pure `None → odoo_version` default-ref substitution helper (SHA lookup deferred to 2b).

### Modified Capabilities
- None. The `compose()` "preserve core.ref=None untouched" requirement is preserved, not changed; 2a is purely additive.

## Approach

TDD domain-first. Add both helpers as pure functions on/near the existing manifest
domain (`schema.py`, `lockfile.py`). Serialization becomes a real contract with a
`schema_version` constant and byte-stable output for reliable `git diff` / drift.
import-linter unchanged (still 2 contracts). CLI `_load_lock` should later consume
the shared deserialize helper (wiring proper belongs to 2b).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/manifest/schema.py` | Modified | pure `resolve_default_ref` helper (no model mutation) |
| `src/odoo_forge/manifest/lockfile.py` | Modified | `schema_version` field + canonical (de)serialize helpers |
| `openspec/specs/manifest/spec.md` | Modified | add `lockfile-format` + `ref-resolution` requirements |
| `tests/manifest/` | New | default-ref cases + byte-stable serialization round-trip |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Helper accidentally invoked inside `compose()`, breaking Slice 1 scenario | Med | Keep helper standalone; regression test asserts composed `core.ref` stays `None` |
| `schema_version` breaks Slice-1-era `project.lock` | Low | No released users; version starts at 1, deserialize tolerates/documents absence |
| Non-deterministic key order weakens drift detection | Med | Contract mandates sorted keys + fixed indent; round-trip byte-equality test |

## Rollback Plan

Pure additive change in the existing `src/odoo_forge/manifest/` tree; revert the
branch. No adapter, no CLI writer, no dependency or import-linter change — nothing
to migrate back.

## Dependencies

- None new. Existing pydantic v2 + stdlib `json`. No git, no network.

## Success Criteria

- [ ] `resolve_default_ref` returns `odoo_version` when `core.ref is None`, echoes an explicit ref otherwise; `compose()` still leaves `core.ref` untouched (Slice 1 scenario stays green).
- [ ] `project.lock` serialization emits `schema_version`, sorted keys, fixed indentation; serialize→deserialize→serialize is byte-identical.
- [ ] import-linter stays 2 kept / 0 broken (no adapter added).
- [ ] Full domain suite green; diff well under the 400-line review budget.

## Review-workload forecast
Small, pure, single-package, no I/O — expected well under 400 lines. Single PR, `review-readability` sufficient; no 4R fan-out required.
