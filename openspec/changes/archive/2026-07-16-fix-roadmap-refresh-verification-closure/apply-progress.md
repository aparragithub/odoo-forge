# Apply Progress: Fix Roadmap Refresh Verification Closure

## Status: Apply Complete — Ready for sdd-verify

## Immutable Parent Evidence

- Snapshot: `evidence/parent-verify-fail.md`; source: parent `verify-report.md`.
- SHA-256: `0fbb60e3b0aba12a46cc26a69c57b40ffb26fa1c60adde5946c0ee9018d084c4`.
- Receipt: `evidence/parent-verify-fail.sha256`; parent report was read-only and remains unchanged.

## Parent-Derived Slice Policy

| Parent-local source | Derived requirement |
|---|---|
| Parent `tasks.md:14–17` | `Decision needed before apply: No`; `Chained PRs recommended: Yes`; `Chain strategy: feature-branch-chain`; `400-line budget risk: High`. |
| Parent `apply-progress.md:28–29,79–80,102` | PR 0: 387 authored; PR 1: 375 changed; PR 2: 109 authored changed lines, each ≤400. |
| Parent `tasks.md:52`; `apply-progress.md:113` | Exact inherited exclusion: Unit 4 only; parent records that no Unit 4 work was started. |

## Review Boundary Decision

Historical S0–S3 counts are logical apply records only. The native staged projection binds all 11 child paths as one user-approved high-tier full-4R target; its live immutable target and receipt are authoritative, and prior numeric estimates are superseded.

Slice 0 is evidence/planning only: 240 authored changed lines (237 additions + 3 deletions), within its 193–240 forecast and the parent-derived ≤400 cap. Its changed-path boundary is the child snapshot, receipt, `apply-progress.md`, the two `tasks.md` checkboxes, and the slice-alignment correction in `design.md`. It starts at the failed parent report and ends at that immutable evidence and policy record. It excludes Unit 4 and all executable, validator, test, HTML, portfolio, and parent-report changes.

## TDD Cycle Evidence

| Task | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|
| 1.1 | N/A (new evidence) | N/A — evidence-only; no executable behavior | `cmp` + SHA receipt passed | N/A — one immutable byte contract | None needed |
| 1.2 | N/A (planning record) | N/A — evidence-only; no executable behavior | parent-local source assertions passed | N/A — no behavior branch | None needed |
| 2.1 | ✅ 19 passing focused baseline | ✅ 12 contract tests written first | Not attempted — RED-only slice | Covered by distinct valid/invalid contract scenarios | None — production is forbidden in Slice 1 |
| 2.2 | ✅ 19 passing focused baseline | ✅ `uv run pytest docs/tools/platform_portfolio/test_validate.py -q`: 12 expected RED failures, 19 passed | Not attempted — RED-only slice | Failure inventory spans all specified contracts | None needed |
| 3.1 | ✅ 12 RED / 19 pass | ✅ Slice 1 contracts | ✅ 31 focused tests passed | ✅ process, evidence, policy, snapshot cases | ✅ pure helpers/failure mapping |
| 3.2 | ✅ HTML ownership RED | ✅ exact metadata/link contract | ✅ repository validator clean | ✅ valid S62 retained; bad fixtures reject | ✅ bounded HTML marker only |
| 3.3 | ✅ 31 focused tests passed | N/A — verification task | ✅ renderer, CLI, Ruff, and full suite passed | N/A | None needed |

No pytest RED test was created or run: Slice 0 adds no executable production behavior, and the assigned tasks require byte/policy evidence rather than fabricated validator coverage. Slice 1 remains the first RED-test slice.

## Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused check | `cmp -s openspec/changes/refresh-platform-roadmap-after-stabilization/verify-report.md openspec/changes/fix-roadmap-refresh-verification-closure/evidence/parent-verify-fail.md && (cd openspec/changes/fix-roadmap-refresh-verification-closure/evidence && sha256sum -c parent-verify-fail.sha256)` — exit 0; byte identity and expected hash verified. |
| Runtime harness | N/A: immutable evidence/planning only; no executable/runtime boundary changed. |
| Whitespace check | `for f in evidence/parent-verify-fail.sha256 apply-progress.md; do git diff --no-index --check /dev/null openspec/changes/fix-roadmap-refresh-verification-closure/$f >/dev/null || test $? -eq 1; done` — exit 0; non-snapshot artifacts clean. The immutable snapshot is exempt: it inherits canonical parent Markdown trailing spaces, and byte identity/hash are mandatory. |
| Rollback boundary | Remove only this child `evidence/` directory and `apply-progress.md`, restore the two Slice 0 checkboxes, and restore the prior slice numbering in `design.md`; do not alter the parent report. |

## Next Batch

## Slice 1: Strict RED Tests and Fixtures

Only `docs/tools/platform_portfolio/test_validate.py` changed. The 12 RED tests cover canonical status; fixed-process canonical argv/cwd/shell=False and five executable decoys with no fallback; exact guide link; valid S62; active-claim rejection, reasoned-gap pass, and missing-gap failure; fabricated evidence; HTML ownership/cardinality; and snapshot byte/hash mismatches.

| Evidence | Exact result |
|---|---|
| Safety net | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 0; 19 passed in 0.20s (pre-existing coverage no-data warnings). |
| Focused RED | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 1; 12 failed, 19 passed in 0.36s. Failures are expected missing behavior: canonical status, exact link, ownership/cardinality assertions, missing fixed-process/injectable-renderer seams, and missing evidence/slice/snapshot/closure APIs. No syntax, import, or fixture failure occurred. |
| Runtime harness | N/A: test-only RED slice; production behavior and runtime boundary are intentionally unchanged. |
| Rollback boundary | Revert Slice 1 additions in `test_validate.py`, the two Phase 2 checkboxes, and this Slice 1 progress record only. |
| Review budget | 180 authored changed lines: 162 test additions + 14 progress additions + 2 checkbox additions + 2 checkbox deletions; ≤400. |

Slice 2 / Phase 3 tasks 3.1–3.3 only: implement the failing contracts, refactor, and run runtime/quality verification. Base it on Slice 1 and target the immediate previous feature-branch-chain branch.

## Slice 2: GREEN, Refactor, and Runtime Verification

`validate.py` now runs only the canonical renderer with `--check`, maps fail-closed results, validates exact HTML ownership/link/state and parent-local evidence, and preserves valid S62. `platform-architecture.html` adds only verified hand-authored ownership metadata; `portfolio.json` is byte-unchanged.

| Evidence | Exact result |
|---|---|
| Focused GREEN | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 0; 31 passed in 0.32s. |
| Renderer runtime | `sg docker -c 'docs/diagrams/render-current-implementation.sh --check'` — exit 0; SVG is current. |
| Validator CLI | `sg docker -c 'uv run python docs/tools/platform_portfolio/validate.py --root .'` — exit 0; `VALIDATOR: CLEAN — 0 violations`. |
| Quality | Ruff check and format-check for both validator files — exit 0. Full `uv run pytest` — exit 0; 684 passed, 14 deselected in 14.24s. |
| Immutable/protected bytes | Snapshot `cmp` and receipt SHA passed; portfolio SHA-256 before/after: `a0fefb1a5e0b00fe6639b0fdca803f0204c249dd9672b3ec3c723f1d103eb77f`. |
| Rollback boundary | Revert only `validate.py`, `test_validate.py`, the ownership attributes in `platform-architecture.html`, Slice 2 task/progress records; retain parent report and portfolio. |
| Review budget | Slice 2 authored changed lines: 353 (210 validator + 101 tests + 2 HTML + 12 tasks + 28 progress); ≤400. |

Next: orchestrator-only child review and `sdd-verify`, followed by the ordered parent incorporation/review/bind/reverification lifecycle.

## Slice 2 Contract Correction

- RED: focused regressions covered legacy planning helpers, nonexistent evidence, and native review authority boundaries.
- GREEN: contained active evidence must exist; native staged review plus SDD verification own scope/budget enforcement.
- Contracts: exact canonical status/ownership, fixed SHA, all active evidence lists, source-record contradictions, and renderer execution/coherence mapping are enforced.
- Final correction delta: 49 authored lines; Slice 2 remains 353/400.

## Slice 3: Root Parity and Renderer/Evidence Trust Boundary

| Evidence | Exact result |
|---|---|
| RED | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 1; 2 contract failures, 30 passed. |
| GREEN | Focused pytest — exit 0; 33 passed in 0.29s. Full `uv run pytest` — exit 0; 684 passed, 14 deselected in 15.12s. |
| Runtime/quality | Renderer, Ruff check/format, and validator CLI with `--root .` and absolute `$PWD` — exit 0; both CLIs clean. |
| Bytes/rollback | Snapshot cmp/SHA and portfolio SHA unchanged; revert only Slice 3 validator/tests/tasks/progress changes. |
| Review budget | Slice 3 authored changed lines: 161 (≤400). |

## Slice 3 Contract Correction

Removed all caller-supplied compact-review receipt ingestion and helper runtime authority from the validator. Native staged review plus SDD verification own scope/budget enforcement. Added RED/GREEN checks for approved renderer bytes, timeout handling, and non-Markdown active evidence.

| Evidence | Exact result |
|---|---|
| Focused RED/GREEN | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — RED: 3 failed, 32 passed; GREEN: 35 passed. |
| Runtime harness | `sg docker -c 'docs/diagrams/render-current-implementation.sh --check && uv run python docs/tools/platform_portfolio/validate.py --root .'` — exit 0; SVG current and `VALIDATOR: CLEAN — 0 violations`. |
| Quality | Ruff check and format-check for validator and test files — exit 0. |
| Rollback boundary | Revert only renderer/evidence/helper-wiring changes in `validate.py`, matching tests, and these task/progress corrections. |
| Review budget | Correction: 152 additions+deletions, under the 190-line cap; no unrelated files changed. |

## Slice 4: Controlled Live Parent-Report Advancement

The frozen child snapshot and receipt remain immutable. The previous child `verify-report.md` was removed after the first behavior edit so a new review/reverification is required; its prior PASS evidence revision was `sha256:33896648a1464a738a8b72f7ea37db203da8bc632d82d17b504898afcbf6fc10`.

| Evidence | Exact result |
|---|---|
| TDD | Historical PASS-parser matrix superseded; focused regression now proves caller receipt input is rejected and no repository live-report authority exists. |
| Structural boundary | Repository code validates immutable child snapshot/receipt only; parent SDD verification with native review validate/bind owns canonical PASS authority. |
| Quality | Full `uv run pytest`: 684 passed, 14 deselected. Ruff check/format and `git diff --check` passed. |
| Integrity | Parent/snapshot `cmp` and receipt SHA passed; portfolio SHA `a0fefb1a5e0b00fe6639b0fdca803f0204c249dd9672b3ec3c723f1d103eb77f`; renderer SHA `526e20a35ace9f4d198a157ddc7e4e0315fe7b208c021099b7a3898c8ee662ed`. |
| Review budget | Slice 4: 396/400 additions+deletions (93 tests, 70 validator, 21 apply, 16 tasks, 196 removed stale report). |

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 5.4 | N/A — evidence task | Gates recorded above | Removed stale child verify report |

## Slice 5: Staged Dependency Separation

The pure `validate_parent_apply_status` contract is for parent SDD verification against its authoritative artifact; child repository validation does not read foreign parent OpenSpec status. The stale failed child report was removed after implementation; prior evidence revision: `sha256:bd614e7d4d24c96411114e7156916a85169590040b622861d0eda7c84235d0d4` (2 blockers, 2 critical findings).

### Intended Native Staged Target (13 paths)

1. `docs/specs/platform/platform-architecture.html`
2. `docs/tools/platform_portfolio/test_validate.py`
3. `docs/tools/platform_portfolio/validate.py`
4. `docs/diagrams/odoo-forge-current-implementation.mmd`
5. `docs/diagrams/odoo-forge-current-implementation.mmd.svg`
6. `openspec/changes/fix-roadmap-refresh-verification-closure/apply-progress.md`
7. `openspec/changes/fix-roadmap-refresh-verification-closure/design.md`
8. `openspec/changes/fix-roadmap-refresh-verification-closure/evidence/parent-verify-fail.md`
9. `openspec/changes/fix-roadmap-refresh-verification-closure/evidence/parent-verify-fail.sha256`
10. `openspec/changes/fix-roadmap-refresh-verification-closure/exploration.md`
11. `openspec/changes/fix-roadmap-refresh-verification-closure/proposal.md`
12. `openspec/changes/fix-roadmap-refresh-verification-closure/specs/platform-portfolio-documentation-integrity/spec.md`
13. `openspec/changes/fix-roadmap-refresh-verification-closure/tasks.md`

This is planning evidence only. Native staged review authenticates the actual tree and paths; foreign parent OpenSpec paths are excluded.

| Evidence | Exact result |
|---|---|
| TDD | Safety net: 36 focused tests passed. RED: 1 failed, 36 passed. GREEN: 37 focused tests passed; target-block and isolated stale-Mermaid simulation pass without claiming native authority. |
| Gates | Full pytest: 684 passed, 14 deselected. Ruff, renderer, relative/absolute CLI, snapshot SHA/cmp, portfolio/renderer hashes, and whitespace passed. |
| Staged orchestration | PASS — exact 13 paths, zero parent OpenSpec/Unit4; isolated post-recording archive: 37 focused tests, renderer current, relative/absolute CLI clean without `apply-progress-status` or `stale-claim`, snapshot SHA receipt and staged whitespace passed. Native review binds the final tree to avoid a self-referential hash claim. |
| Review budget | Retained Slice 5 delta: 259 authored changed lines across eight files; generated failed `verify-report.md` deletion is recorded separately and excluded. |
| Rollback | Revert only Slice 5 validator/tests/tasks/progress and restore the removed failed child report; never stage or alter parent artifacts. |
