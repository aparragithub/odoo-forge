## Verification Report — Phase 2 Slice 2a (Pure Resolution Prep)

**Change**: phase-2-slice-2a-resolution-prep
**Branch**: sdd/phase-2-slice-2a-resolution-prep (confirmed)
**Mode**: Strict TDD | Artifacts: full (spec + design + tasks + apply-progress)
**Verdict**: PASS WITH WARNINGS
**Ready for archive**: YES (amend spec prose W1 during archive fold-in)

### Gate Evidence (verbatim)
- `uv run pytest`: **48 passed in 0.28s** (0 failed, 0 skipped; baseline was 28 → +20). Relevant 4-file subset: 27 passed.
- `uv run lint-imports`: "Analyzed 20 files, 27 dependencies. Core never imports infrastructure or framework KEPT. Core never imports the CLI KEPT. **Contracts: 2 kept, 0 broken.**"
- `git diff main --stat`: **6 files changed, 210 insertions(+), 1 deletion(-)** — well under 400-line budget.
  - src/odoo_forge/manifest/lockfile.py +27/-1
  - src/odoo_forge/manifest/resolution.py +20 (new)
  - tests/manifest/test_composition.py +15
  - tests/manifest/test_drift.py +47
  - tests/manifest/test_lockfile_format.py +76 (new)
  - tests/manifest/test_resolution.py +26 (new)

### Scenario → Test Coverage Map (all PASSED at runtime)
Req 1 — resolve_default_ref (pure helper):
- None→odoo_version → test_none_ref_resolves_to_odoo_version ✓
- Explicit ref preserved → test_explicit_ref_preserved_unchanged ✓
- Non-mutating (core.ref stays None) → test_helper_does_not_mutate_core ✓
- compose() regression: composed core.ref stays None AND compose does NOT call resolve_default_ref → test_compose_regression_core_ref_stays_none_and_helper_never_called ✓ (asserts chain[0].ref is None AND `"resolve_default_ref" not in inspect.getsource(composition)`). composition.py confirmed byte-untouched (no import, no call).

Req 2 — versioned canonical lockfile:
- schema_version present (int == LOCKFILE_SCHEMA_VERSION) → test_serialize_includes_schema_version_field ✓
- Stable key ordering / list order preserved → test_to_canonical_json_sorts_keys_preserves_layer_order ✓
- Byte-stable round-trip (serialize→deserialize→serialize) → test_round_trip_serialize_deserialize_serialize_byte_identical ✓
- Legacy doc (absent schema_version) tolerated → defaults to 1 → re-serializes explicit → test_legacy_lock_without_schema_version_defaults_to_one_and_reserializes_explicit ✓

Drift back-compat:
- Slice-1-era lock dict yields identical DriftReport → test_slice1_era_lock_dict_yields_identical_drift_report ✓ (validates legacy dict, defaults schema_version=1, `legacy_report == explicit_report`).

### TDD Compliance
| Check | Result |
|-------|--------|
| TDD Evidence reported | ✅ Found in apply-progress |
| All tasks have tests | ✅ 22/22 |
| RED confirmed (test files exist) | ✅ all 4 files present |
| GREEN confirmed (tests pass now) | ✅ 27/27 relevant, 48/48 suite |
| Triangulation | ✅ resolution 3 cases, lockfile 4 cases |
| Safety net (modified files) | ✅ test_composition/test_drift additive to green suites |

### Assertion Quality Audit
✅ All assertions verify real behavior. No tautologies, no ghost loops, no smoke-only tests. The compose regression uses inspect.getsource to prove non-wiring (strong structural assertion). No implementation-detail coupling of concern.

### Issues
- **W1 (WARNING — resolved-by-spec-amendment)**: Spec Req 2 prose names the helpers `serialize()`/`deserialize()`, but design, tasks, and implementation use `to_canonical_json()`/`from_json()`. This is a naming divergence ONLY — every behavioral contract (schema_version, sorted keys, byte-stable round-trip, legacy tolerance) is fully satisfied. NOT a contract violation and NOT blocking: no caller in 2a references `serialize()`, so zero runtime impact. Recommendation: amend the spec wording to `to_canonical_json()`/`from_json()` during the archive fold-in so the permanent spec does not enshrine a non-existent method name. Adjudicated: WARNING, not CRITICAL.
- **S1 (SUGGESTION)**: The "key ordering stable across runs" scenario literally describes two Lockfile instances built in different field insertion order. The covering test proves sorted top-level keys + preserved list order + byte-stable round-trip instead (Pydantic fixes field insertion order at class-definition time, so the literal scenario is not cleanly constructible via the constructor). Intent is fully covered; no action required.

### Design Coherence
✅ Implementation matches design exactly: module location (resolution.py), constant name (LOCKFILE_SCHEMA_VERSION=1), canonicalization strategy (json.dumps sort_keys=True, indent=2, +"\\n"), compute_manifest_hash left untouched and distinct. No deviations. import-linter gate unchanged (no new adapter/contract) as designed.

### CRITICALs
None.

**Final**: 0 CRITICAL, 1 WARNING (W1, non-blocking, spec-amendment), 1 SUGGESTION (S1). PASS WITH WARNINGS. Ready for sdd-archive.
