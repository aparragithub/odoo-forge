# Tasks: Phase 2 Slice 2a — Pure Resolution Prep

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 150–250 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | ref-resolution helper + lockfile-format + drift back-compat regression, all pure | PR 1 | base = main; single PR, review-readability sufficient, no 4R fan-out |

## Phase 1: Foundation — ref-resolution helper

- [x] 1.1 RED: write `tests/manifest/test_resolution.py::test_none_ref_resolves_to_odoo_version`
- [x] 1.2 GREEN: create `src/odoo_forge/manifest/resolution.py` with `resolve_default_ref(core, odoo_version)` returning `odoo_version` when `core.ref is None`
- [x] 1.3 RED: write `test_resolution.py::test_explicit_ref_preserved_unchanged`
- [x] 1.4 GREEN: extend `resolve_default_ref` to return `core.ref` unchanged when set
- [x] 1.5 RED: write `test_resolution.py::test_helper_does_not_mutate_core`
- [x] 1.6 GREEN: confirm no-mutation invariant holds (refactor only if assertion fails)
- [x] 1.7 RED: write `test_composition.py::test_compose_regression_core_ref_stays_none_and_helper_never_called` (asserts composed `core.ref is None`; asserts `composition.py` does not import/call `resolve_default_ref`)
- [x] 1.8 GREEN: confirm `src/odoo_forge/manifest/composition.py` stays untouched and the Slice 1 "preserve `core.ref=None`" scenario still passes

## Phase 2: Core Implementation — lockfile-format contract

- [x] 2.1 RED: write `tests/manifest/test_lockfile_format.py::test_serialize_includes_schema_version_field`
- [x] 2.2 GREEN: add `LOCKFILE_SCHEMA_VERSION = 1` constant and `schema_version: int = LOCKFILE_SCHEMA_VERSION` field to `Lockfile` in `src/odoo_forge/manifest/lockfile.py`
- [x] 2.3 RED: write `test_lockfile_format.py::test_to_canonical_json_sorts_keys_preserves_layer_order`
- [x] 2.4 GREEN: implement `Lockfile.to_canonical_json()` (`json.dumps(model_dump(mode="json"), sort_keys=True, indent=2) + "\n"`)
- [x] 2.5 RED: write `test_lockfile_format.py::test_round_trip_serialize_deserialize_serialize_byte_identical`
- [x] 2.6 GREEN: implement `Lockfile.from_json(raw)` classmethod (`cls.model_validate(json.loads(raw))`)
- [x] 2.7 RED: write `test_lockfile_format.py::test_legacy_lock_without_schema_version_defaults_to_one_and_reserializes_explicit`
- [x] 2.8 GREEN: confirm/adjust `Lockfile` field default so absent `schema_version` validates to `1` and re-serialization emits it explicitly

## Phase 3: Integration — drift back-compat regression

- [x] 3.1 RED: write `tests/manifest/test_drift.py::test_slice1_era_lock_dict_yields_identical_drift_report` (build a lock dict with no `schema_version` key, `model_validate` it, run `detect_drift`, compare against a `DriftReport` built from an explicit-`schema_version=1` `Lockfile`)
- [x] 3.2 GREEN: confirm `detect_drift()` and `Lockfile` validation require no production change; both `DriftReport` results are identical

## Phase 4: Verification

- [x] 4.1 Run `uv run pytest` — confirm every RED test above is GREEN, no skips (48 passed)
- [x] 4.2 Run `uv run lint-imports` — confirm gate stays 2 kept / 0 broken (no new contract, no adapter) — confirmed
- [x] 4.3 Run `git diff --stat` against base — confirm total changed lines are well under the 400-line review budget (~210 lines total)

All 22 tasks complete. See sdd/phase-2-slice-2a-resolution-prep/apply-progress for TDD evidence and commit hashes.
