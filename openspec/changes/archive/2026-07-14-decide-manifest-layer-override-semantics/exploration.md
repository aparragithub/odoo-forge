## Exploration: decide-manifest-layer-override-semantics

### Current State

`PublishedLayer` and `Override` are accepted by the Pydantic manifest schema, but their end-to-end behavior is intentionally incomplete.

- `PublishedLayer` is a discriminated `Layer` variant with `source`, `version`, optional edition gating, and optional projection category. `compose()` includes it in the onion chain and validates edition coherence. `plan_projection()` can classify it, but `build_lock()` only resolves the core and `GitLayer`; published layers are omitted from `project.lock`.
- `Override` contains `layer`, `repo`, `fork`, and `ref`. Composition validates that the target layer exists, is a `GitLayer`, and contains the named repository. `build_lock()` does not apply `fork` or `ref`; the current test explicitly proves that the original repository URL/ref is pinned.
- Existing tests therefore characterize acceptance and deferred behavior, not a complete public contract. Current fixtures use both concepts, including published layers and a Git repository override.
- The canonical manifest spec defines the layer union, composition validation, lock writing, and workspace projection, but has no normative published-registry resolution or override-application requirement yet. It explicitly leaves I/O resolution to injected ports and preserves pure-core boundaries.
- Current OpenSpec context requires Python/Pydantic pure core, injected protocols, strict TDD, deterministic lock serialization, and adapter-specific I/O boundaries.
- `docs/specs/platform/portfolio.json` is authoritative: `CAP-MANIFEST` is achieved (`AC-CAP-MANIFEST-READY`, evidence S0) and hands off to project-catalog and deployment-spec capabilities. This decision must refine that achieved manifest contract, not redefine portfolio status or activate unrelated work.
- Unit 2 of `docs/specs/2026-07-14-stabilization-roadmap.md` explicitly requires one authority-backed decision for each feature, accepted examples, and migration/compatibility impact. It identifies source resolution and override application as deferred. Unit 1 is complete through issue #55 / PR #62; this exploration does not revisit it.

### Affected Areas
- `src/odoo_forge/manifest/schema.py` — current `PublishedLayer` and `Override` declarations.
- `src/odoo_forge/manifest/composition.py` — current target validation and precedence-independent structural checks.
- `src/odoo_forge/manifest/locking.py` — published layers are currently omitted and overrides are currently ignored during resolution.
- `src/odoo_forge/manifest/lockfile.py` — `ResolvedLayer`/`ResolvedRepo` are Git-shaped and need an explicit compatible representation for published artifacts if implementation is selected.
- `src/odoo_forge/ports/source_provider.py`, `src/odoo_forge_registry/provider.py` — existing protocol/registry adapter boundaries are relevant to a future registry resolution design.
- `tests/manifest/test_schema.py`, `test_composition.py`, `test_locking.py`, `tests/cli/test_lock.py` — current contract and deferred-behavior evidence.
- `openspec/specs/manifest/spec.md` — canonical normative manifest baseline to amend only after approval.
- `docs/specs/platform/portfolio.json`, `docs/specs/2026-07-14-stabilization-roadmap.md` — current product/dependency authority and Unit 2 boundary.
- Historical evidence: `docs/specs/2026-07-06-phase-2-slices-roadmap.md` and archived `phase-2-slice-4a-registry-resolution/explore.md` record registry resolution and override application as deferred. They are evidence only, not current requirements.

### Approaches
1. **Implement `PublishedLayer`; implement `Override` for Git layers** — Preserve the accepted manifest vocabulary, resolve published source/version through a dedicated registry-capable boundary, represent its pinned result explicitly in the lock, and apply a validated Git override before ref resolution.
   - Pros: matches existing schema, fixtures, portfolio handoff, and historical intent; preserves reproducible locks; supports published artifacts and local forks without silently ignoring declarations.
   - Cons: requires a precise registry contract, lockfile compatibility strategy, typed registry failures, and precedence tests.
   - Effort: High

2. **Deprecate both concepts** — Keep parsing temporarily for migration, emit actionable warnings, and require Git layers without overrides for new manifests.
   - Pros: avoids designing registry and fork semantics now.
   - Cons: contradicts the deliberate schema vocabulary and existing product-facing examples; removes useful published distribution and local-fork use cases; still requires a migration/versioning policy.
   - Effort: Medium

3. **Remove both concepts** — Reject `type: published` and `overrides` at validation time and migrate all fixtures/users to Git-only manifests.
   - Pros: smallest long-term model.
   - Cons: breaking change with no authority evidence that these use cases are unwanted; conflicts with the existing CAP-MANIFEST shape and deferred-slice record.
   - Effort: Medium

### Recommendation

**PublishedLayer: implement. Override: implement, scoped to GitLayer repository replacement.** Neither concept should be deprecated or removed based on current evidence.

Published layers represent a distinct product use case: consume a versioned, registry-published layer rather than enumerate source repositories. The schema and historical Slice 4a record establish that this was deferred infrastructure, not rejected vocabulary. The implementation must define a registry provider contract, a pinned lock entry (including artifact identity/version/digest or equivalent), and deterministic resolution failures. A published layer remains ordered in the onion chain and cannot be overridden through the Git repository override shape.

Overrides represent a distinct developer/use-case need: temporarily or intentionally substitute one Git repository with a fork and ref. Application precedence should be explicit and deterministic: validate the target first; when an override matches a Git layer/repository, resolve `fork` + `ref` instead of the declared URL + ref; otherwise fail loudly. Duplicate matches, unknown layers/repos, published-layer targets, and invalid combinations should be rejected rather than silently ignored. Manifest hashing must include the declared override, while the lock records the effective source so drift remains visible.

Compatibility and migration should preserve existing manifests that contain declarations. Existing Git-only manifests and legacy locks must continue to work. Existing published declarations currently produce no lock entries, so enabling them requires an explicit lock schema/version migration or a backward-compatible additive entry shape. Existing published-target override declarations are already rejected by composition and should remain invalid, not become silently applicable. Historical lock files must not acquire fabricated published entries during read/round-trip.

The future proposal must resolve the remaining product/contract questions before code: registry API and identity/digest semantics; lock entry shape and schema version; whether override matching is unique by repository basename or URL; duplicate override precedence (recommended: reject); and whether overrides are allowed to target the core layer. It must not modify or advance `CHG-FIRST-DATABASE-ADAPTER` or `sp-data-environments`.

### Risks
- A registry protocol and lock representation could accidentally become Git-shaped and lose artifact digest/version provenance.
- Applying overrides after resolution would pin the wrong source; precedence must be tested at the effective-input boundary.
- Existing published manifests currently compose but are omitted from locks; changing this can expose compatibility issues in validation, projection, drift, and lock consumers.
- Repository-basename matching can be ambiguous across owners; the contract must either reject ambiguity or use a fully qualified identity.
- Treating historical Slice 4a text as a requirement would bypass the current portfolio and Unit 2 authority boundary.
- The prohibited scope is a hard boundary: no changes or advancement to `CHG-FIRST-DATABASE-ADAPTER` or `sp-data-environments`.

### Ready for Proposal

Yes. The exploration supports a proposal for implementation of both concepts, but user/product approval is still required for the registry contract, lock compatibility shape, override identity/precedence, and migration policy. No proposal or runtime implementation should begin until that approval is obtained.
