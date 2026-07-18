# Tasks: Harden catalog default validation against blank strings

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~90-120 (small helper + 3 line swaps + ~6 additive tests) |
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

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Blank-default validation hardening (helper + swap + tests) | PR 1 | `uv run pytest tests/project_catalog/test_resolver.py -q` | N/A — pure in-memory predicate, no external I/O to exercise | Revert single commit touching `validation.py` + `test_resolver.py` |

## Phase 1: RED — Write Failing Tests

- [x] 1.1 In `tests/project_catalog/test_resolver.py`, add `test_returns_invalid_catalog_when_data_policy_default_is_blank` using `_resolve_incomplete(defaults=CatalogDefaults(data_policy="", target="staging"))`; assert `invalid_fields == ["data_policy_default"]` and `reason_code == "missing:data_policy_default"` (spec scenario: blank data_policy).
- [x] 1.2 Add `test_returns_invalid_catalog_when_target_default_is_whitespace_only` using `_resolve_incomplete(defaults=CatalogDefaults(data_policy="masked-copy", target="   "))`; assert `invalid_fields == ["target_default"]` and `reason_code == "missing:target_default"` (spec scenario: whitespace-only target).
- [x] 1.3 Add `test_returns_invalid_catalog_when_both_defaults_are_blank` using `_resolve_incomplete(defaults=CatalogDefaults(data_policy="", target="   "))`; assert `invalid_fields == ["data_policy_default", "target_default"]` and `reason_code == "missing:data_policy_default+target_default"` (spec scenario: both blank preserves order).
- [x] 1.4 Add `test_returns_invalid_catalog_when_blank_target_combined_with_none_source_context` using `_resolve_incomplete(source_context=None, defaults=CatalogDefaults(data_policy="masked-copy", target="   "))`; assert `invalid_fields == ["source_context", "target_default"]` and `reason_code == "missing:source_context+target_default"` (spec scenario: blank + None fixed order).
- [x] 1.5 Add `test_validate_record_accepts_non_blank_defaults_unchanged` calling `validate_record(_record())` directly (reuse `_record()`), asserting `isinstance(..., ValidatedCatalogRecord)` and `data_policy_default == "masked-copy"`, `target_default == "staging"` — confirms the happy path is untouched (spec scenario: non-blank valid defaults).
- [x] 1.6 Add `test_blank_manifest_ref_or_source_context_out_of_scope_for_blank_checks` documenting that only `is None` classifies `manifest_ref`/`source_context` as invalid: reuse `test_returns_invalid_catalog_when_only_manifest_ref_is_missing`-style assertion via `_resolve_incomplete(manifest_ref=None)` (already covered) — add an explicit regression asserting `_resolve_incomplete(source_context=None)` still yields exactly `["source_context"]` with non-blank defaults present, proving blank-string logic is not applied to typed refs (spec scenario: typed refs out of scope).
- [x] 1.7 Run `uv run pytest tests/project_catalog/test_resolver.py -q` and confirm the four new failing assertions in 1.1-1.4 fail with the current `is None`-only checks (RED confirmed); 1.5 and 1.6 should already pass since they exercise unchanged behavior.

## Phase 2: GREEN — Implement the Fix

- [x] 2.1 In `src/odoo_forge/project_catalog/validation.py`, add module-level private helper directly above `invalid_required_fields`: `def _is_blank(value: str | None) -> bool: return value is None or not value.strip()`.
- [x] 2.2 In `invalid_required_fields`, replace `if record.defaults.data_policy is None:` with `if _is_blank(record.defaults.data_policy):` and `if record.defaults.target is None:` with `if _is_blank(record.defaults.target):`; leave `manifest_ref`/`source_context` checks as `is None`, preserve append order.
- [x] 2.3 In `validate_record`, change the short-circuit condition to `if manifest_ref is None or source_context is None or _is_blank(data_policy) or _is_blank(target):`.
- [x] 2.4 Confirm `_is_blank` is not added to `__all__` in `validation.py` (stays private).

## Phase 3: Verify

- [x] 3.1 Run `uv run pytest tests/project_catalog/test_resolver.py -q` and confirm all tests (new and pre-existing) pass — this is the final gate proving no regression and full spec scenario coverage.
- [x] 3.2 Run `uv run pytest tests/project_catalog/ -q` for the broader `project_catalog` suite to confirm no unrelated fixture or resolver assertion broke.
- [x] 3.3 Diff-review `git diff -- src/odoo_forge/project_catalog/validation.py tests/project_catalog/test_resolver.py` to confirm the change stays scoped to these two files only (per proposal Out of Scope).

## Phase 4: Cleanup

- [x] 4.1 Re-read `validation.py` docstring on `_is_blank` for clarity; no other doc updates required (no public contract change).
