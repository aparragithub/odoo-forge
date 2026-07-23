# Proposal: Refresh Portfolio State for Pipeline Adapter Completion

## Intent

The GitHub Actions pipeline adapter (`CHG-FIRST-PIPELINE-ADAPTER`, decision `DPROV-CI`) was
delivered and merged in commit `890f8bb`. The canonical portfolio state file
`docs/specs/platform/portfolio.json` was last regenerated in the earlier chore commit `7736332`
(which only recorded the `DPROV-CI` decision), so it never captured the merge outcome. The
pipeline port, adapter, and change items are therefore still `proposed` while the code, tests,
and decision that satisfy them already exist. This makes the roadmap state file lie about
delivered work, which undermines its role as the single source of truth for what is `achieved`.

## Scope

### In Scope
- Sync `CHG-FIRST-PIPELINE-ADAPTER` (`sdd_change`) to `achieved` with evidence + `evidence_date`.
- Sync `PORT-PIPELINE` (`port`) to `achieved`, clearing gap `G5`.
- Sync `ADAPTER-PIPELINE-GITHUB` (`adapter`) to `achieved`, clearing gap `G6`.
- Flip the corresponding `acceptance[].status` entries to `achieved` and attach evidence source IDs.
- Add pipeline-adapter evidence entries to `meta.evidence_catalog` if a referenced source ID is missing.
- If strictly necessary and clearly consistent, reflect the same status in `docs/diagrams/*.mmd`.

### Out of Scope
- Any change under `src/` or `tests/` (owned by the parallel CLI-wiring change).
- Wiring `GitHubActionsPipelineProvider` into the CLI composition root.
- `SP-DELIVERY-AUTOMATION` outcome status (a broad subproject outcome, not the adapter slice).
- `ADAPTER-PIPELINE-GITLAB` and any second CI ecosystem (deferred by `DPROV-CI`/`DP`).
- Editing unrelated `items`, `decisions`, `transitions`, or `transfers`.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- None (state-data refresh only; no spec-level requirement changes).

## Approach

Perform a surgical, in-place JSON edit of the three stale items in `portfolio.json`, preserving
document structure and valid JSON. For each item, set `status: "achieved"`, set an
`evidence_date`, replace empty `evidence: []` with source IDs referencing the merged adapter work
(commit `890f8bb`, the `src/odoo_forge_pipeline_github/` adapter, the `PipelineProvider` port, and
their tests), clear the `gaps` array, and mirror the same on the nested `acceptance` entry. Add
any missing evidence source IDs to `meta.evidence_catalog`. Verify JSON validity after editing.
Leave every other array element byte-identical.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `docs/specs/platform/portfolio.json` | Modified | 3 items + acceptance flipped to `achieved`; evidence catalog extended |
| `docs/diagrams/*.mmd` | Modified (conditional) | Only if a diagram encodes pipeline adapter status and must stay consistent |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Malformed JSON breaks the canonical state file | Med | Validate JSON after edit; edit only the three target items |
| Merge conflict with parallel `src/` change | Low | Hard scope confines edits to the doc/state surface only |
| Referencing evidence IDs that do not exist | Med | Add missing IDs to `meta.evidence_catalog`; reuse existing DB-adapter pattern |
| Over-syncing (e.g. `SP-DELIVERY-AUTOMATION`) | Low | Explicit out-of-scope list; only adapter-slice items move |

## Rollback Plan

`git revert` the single commit touching `docs/specs/platform/portfolio.json`. The file is
self-contained state data with no runtime dependency, so reverting restores the prior `proposed`
state with zero side effects on code or tests.

## Dependencies

- Merged commit `890f8bb` (pipeline adapter) — already present on `main`.
- Decision `DPROV-CI` = GitHub Actions — already `decided` (commit `7736332`).

## Success Criteria

- [ ] `PORT-PIPELINE`, `ADAPTER-PIPELINE-GITHUB`, `CHG-FIRST-PIPELINE-ADAPTER` are `achieved` with evidence and `evidence_date`.
- [ ] Their nested `acceptance[].status` are `achieved` and their `gaps` arrays are empty.
- [ ] `portfolio.json` remains valid JSON; no unrelated items/decisions/transitions/transfers changed.
- [ ] No files under `src/` or `tests/` are touched.
