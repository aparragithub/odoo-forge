# Tasks: Refresh Portfolio State for Pipeline Adapter Completion

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 10-20 (single minified JSON line; field-level edits) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Refresh `docs/specs/platform/portfolio.json` (3 items + evidence_catalog) | PR 1 | JSON-validity check (see Phase 3) | N/A — pure state-data edit, no runtime behavior to exercise | `git revert` the single commit touching `portfolio.json` |

## Phase 1: Evidence Catalog Preparation

- [x] 1.1 In `docs/specs/platform/portfolio.json`, add new `meta.evidence_catalog` entries `S71`-`S74` (or next free IDs after `S70`) describing: merged commit `890f8bb`, `src/odoo_forge_pipeline_github/` adapter source, the `PipelineProvider` port definition, and the adapter's test module — reuse the DB-adapter catalog string pattern (e.g. `"src/odoo_forge_pipeline_github/adapter.py"`).

## Phase 2: Item State Transitions

- [x] 2.1 Set `PORT-PIPELINE` item: `status:"achieved"`, `evidence_date` to the merge date of `890f8bb`, `acceptance[0].evidence` to the new evidence IDs, `acceptance[0].status:"achieved"`, `acceptance[0].gaps:[]` (clears `G5`).
- [x] 2.2 Set `ADAPTER-PIPELINE-GITHUB` item: same fields as 2.1, clearing gap `G6`.
- [x] 2.3 Set `CHG-FIRST-PIPELINE-ADAPTER` item (`kind:"sdd_change"`): same fields as 2.1, clearing gap `G0`.
- [x] 2.4 Confirm the separate `blocked_product_placeholder` transfer entry referencing `PORT-PIPELINE`/pipeline-adapter (different top-level array, unrelated to the 3 named items) is left byte-identical — do not edit it.
- [x] 2.5 Leave `ADAPTER-PIPELINE-GITLAB` and `SP-DELIVERY-AUTOMATION` entries untouched.
- [x] 2.6 (Conditional) If any `docs/diagrams/*.mmd` file explicitly encodes `PORT-PIPELINE`/`ADAPTER-PIPELINE-GITHUB`/`CHG-FIRST-PIPELINE-ADAPTER` status, update it to match; otherwise skip.

## Phase 3: Validation (no pytest — JSON-validity + no-stray-edits check)

- [x] 3.1 RED: confirm current state — parse `docs/specs/platform/portfolio.json` and assert the 3 target items still show `status:"proposed"` before editing (baseline check).
- [x] 3.2 GREEN: after edits, parse `docs/specs/platform/portfolio.json` with a standard JSON parser and assert it succeeds (validates `Portfolio file remains valid JSON` requirement).
- [x] 3.3 GREEN: assert all 3 items now report `status:"achieved"`, non-null `evidence_date`, non-empty `evidence`, and empty `gaps`; assert nested `acceptance[]` mirrors the same.
- [x] 3.4 GREEN: assert every evidence ID referenced by the 3 items exists as a key in `meta.evidence_catalog`.
- [x] 3.5 GREEN: diff `docs/specs/platform/portfolio.json` against the pre-change version and assert only the 3 named items + `evidence_catalog` additions changed — no other item, decision, transition, or transfer entry differs.
- [x] 3.6 GREEN: confirm `git diff --stat` shows no files under `src/` or `tests/` in this change's edits (a concurrent, unrelated change already had `tests/manifest/test_module_deps.py` modified before this session started; not touched by this change).

## Phase 4: Cleanup

- [x] 4.1 Re-read the final `portfolio.json` diff to confirm it matches the proposal's Success Criteria checklist exactly.
