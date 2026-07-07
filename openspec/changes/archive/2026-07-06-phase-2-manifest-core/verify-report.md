# Verification Report — phase-2-manifest-core (Slice 1: Manifest Core) — RE-VERIFY

**Mode**: hybrid (files + Engram) · **Strict TDD**: active · **Delivery**: local-only (no push/merge/PR)
**Verdict**: PASS WITH WARNINGS — C1 resolved; ready for archive.
**Executive summary**: Re-verify after the spec amendment (obs #2290, topic `sdd/phase-2-manifest-core/scope-boundary`). 23/23 tests pass, 2/2 import-linter contracts kept, `forge validate` fire test exits 0. The prior CRITICAL C1 (spec required `core.ref` None→branch resolution that no Slice-1 code implements) is **RESOLVED**: the amended spec now treats `core.ref: None` as valid unresolved intent and requires `compose()` to preserve it unchanged — which is exactly what `compose()` does. One residual WARNING remains: no explicit test asserts "composition preserves None" (the amendment's new regression guard).

## Command Evidence (actual output, this run)
| Check | Command | Result |
|---|---|---|
| Test suite | `uv run pytest -v` | 23 passed, 0 failed, 0 skipped (0.10s) — expected 23 ✓ |
| Arch boundary | `uv run lint-imports` | Analyzed 19 files, 25 deps. `core-is-pure` KEPT, `core-ignores-cli` KEPT. 2 kept, 0 broken ✓ |
| Fire test | `uv run forge validate --manifest tests/fixtures/odoo-idp.project.yaml` | "…is valid", exit 0 ✓ |
| Artifact structure (W2) | `fd` over change dir | Only flat `spec.md`; NO `specs/` subdir — matches corrected Engram #2283 ✓ |

## C1 Resolution Analysis (the amendment)
The amended requirement "Core layer is a first-class field" now states: `core.ref: None` MUST be accepted as valid unresolved intent, and `compose()` MUST preserve `None` unchanged (no resolve, no mutate, no reject); None→`odoo_version` branch resolution is OUT OF SCOPE, deferred to the resolution/materialization slice. Scenario renamed to "Unresolved core ref is valid and untouched by composition".

- **(a) Consistency**: PASS. `compose()` (composition.py:16) builds `chain = [manifest.core]` verbatim — no resolution branch exists. `design.md` (CoreLayer, line 86) and schema.py both defer resolution. Spec, design, and code now agree.
- **(b) Coverage** of the three THEN clauses:
  - parse → `core.ref is None`: **explicit** — `test_core_default_url_and_ref_none` (test_schema.py:27-31).
  - compose succeeds on a None-ref manifest: **exercised** — `test_onion_order_core_first_client_last` composes a `_base_kwargs` manifest (no `core` key → ref None) with no error.
  - composed core layer `ref` remains `None`: **NO explicit assertion** — `test_onion_order` only asserts `isinstance(chain[0], CoreLayer)`, not `chain[0].ref is None`.

**Conclusion**: C1 is cleared as a spec-vs-code conflict. The requirement is now satisfied by implementation (trivial verbatim passthrough) and covered in aggregate. The one missing piece is a single explicit assertion locking the "compose preserves None" invariant — a WARNING-level coverage precision gap (W1 below), not a blocker.

## Spec Compliance Matrix (requirement → test/impl → verdict)
| Capability / Requirement | Scenario | Evidence | Verdict |
|---|---|---|---|
| manifest-schema: Core is first-class field | Unresolved core ref valid + untouched by composition | parse-None: `test_core_default_url_and_ref_none`; compose-no-error on None-ref: `test_onion_order_core_first_client_last`; impl: `compose()` returns `manifest.core` verbatim | PASS (with W1 — no explicit "ref stays None post-compose" assertion) |
| manifest-schema: Core is first-class field | Overridden core url | `CoreLayer.url: str` accepts override; no explicit fork test | PASS (weak) — W2 |
| manifest-schema: Core field defaults | type/url/ref defaults | `test_manifest_requires_core_field`, `test_core_default_url_and_ref_none` | PASS |
| manifest-schema: Per-artifact edition gating | Enterprise repo nested rejected | `test_community_rejects_nested_enterprise_repo` (match odoo-argentina-ee) | PASS |
| manifest-schema: Per-artifact edition gating | Enterprise manifest accepts repo | `test_enterprise_manifest_accepts_same_repo` | PASS |
| manifest-schema: Discriminated union | Single-member error | `test_discriminated_layer_single_error`, `test_malformed_fixture_yields_single_scoped_error` | PASS |
| manifest-schema: Hash from in-memory model | Same-model → same hash | `test_hash_stable_across_key_order`, `test_hash_differs_when_content_differs` | PASS |
| onion-composition: order + validate, no I/O | Core-first/client-last | `test_onion_order_core_first_client_last` | PASS |
| onion-composition | Override → missing layer/repo fails | `test_override_missing_layer_raises_no_io`, `test_override_missing_repo_in_existing_layer_raises` | PASS |
| onion-composition | odoo-idp fire test composes | `test_odoo_idp_fire_test_composes_cleanly` (≥17 repos) | PASS |
| drift-detection: pure 3-input | Clean / stale / state+None | `test_clean_state_is_clean`, `test_manifest_changed_lock_stale`, `test_lock_state_drift_and_none_inputs` | PASS |
| forge-validate-cli: delegates to core | valid / malformed / drift | `test_valid_manifest_exits_zero`, `test_malformed_manifest_single_cause_error_nonzero_exit`, `test_reports_manifest_lock_drift_when_lock_exists` | PASS |
| source-provider-port: interface only | Protocol conformance + purity | `test_conforming…`, `test_non_conforming…`, `lint-imports` 2/2 kept | PASS |

## TDD Compliance (Strict mode)
Every RED task maps to an existing, passing test; 6 test modules present; 23/23 GREEN; triangulation present (hash stable/differs, drift 4-way, override 2-way, edition reject/accept). No tautologies, ghost loops, or production-code-free assertions. ✅

## Issues
### CRITICAL
- None. (Prior C1 resolved by the spec amendment; spec, design, and `compose()` are now consistent.)

### WARNING
- **W1 (was C1 residue) — "compose preserves None" has no explicit assertion.** The amended scenario's key regression clause ("composed core layer's `ref` remains `None`, no resolution attempted") is satisfied by trivial passthrough and exercised indirectly, but no test asserts `compose(m)[0].ref is None`. A future erroneous resolution added to `compose()` would not be caught. Recommend a one-line hardening test. NOT blocking (requirement satisfied + covered in aggregate).
- **W2 — "Overridden core url" scenario** has no explicit fork-url test (only default url exercised).
- **W3 — project.lock on-disk format undocumented**: CLI chose plain JSON of `Lockfile.model_dump(mode="json")`; spec/design constrain drift semantics, not serialization. Document in the persistence slice. Not a conformance failure.
- **W4 — Phase 4 tasks 4.1–4.3 unchecked** in tasks.md; functionally satisfied by this run. Tick at archive.

### SUGGESTION
- **S1** — Hash spec text says `model_dump_json(exclude_none=False)`; impl uses `json.dumps(model_dump(mode="json"), sort_keys=True, separators=…)` — equivalent + design-sanctioned; align spec wording.
- **S2** — Community + PublishedLayer `requires_edition: enterprise` rejection path implemented but untested (only GitLayer/repo covered).

## Resolved Since Prior Report (#2289)
- **C1** → resolved via spec amendment (deferred resolution out of Slice 1). Downgraded to W1 (test-precision only).
- **W2 (prior, artifact drift)** → resolved: Engram #2283 corrected to reflect the single flat `spec.md`; filesystem confirms no `specs/` subdir.

## Final Gate
**READY FOR ARCHIVE (local-only close).** No CRITICAL issues. Spec, design, and implementation are now internally consistent after the amendment; all 23 tests pass, both arch contracts hold, and the fire test succeeds. The remaining items are WARNINGs/SUGGESTIONs — none block archive. Optional (recommended for strict-TDD rigor): a tiny test-only apply adding `assert compose(m)[0].ref is None` for a None-ref manifest to lock the amended regression guard (W1), then tick tasks 4.1–4.3. This is a judgment call; archive may proceed without it since the invariant is proven by inspection and covered in aggregate.
