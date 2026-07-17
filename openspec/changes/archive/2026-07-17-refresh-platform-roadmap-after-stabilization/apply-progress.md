# Apply Progress: Refresh Platform Roadmap After Stabilization

## Status: Apply Complete — Ready for sdd-verify

## Historical Blocker: Pre-Retention Budget Gate (Resolved)

Before the tracker baseline was retained, `feature/refresh-platform-roadmap-after-stabilization`
did not contain this change's untracked planning artifacts. Before that retry's evidence update,
the six artifacts added **351** lines
relative to that tracker: exploration (63), proposal (61), delta spec (69), design (94), tasks
(47), and the prior progress record (17). They now add **382** lines, leaving only **18** authored
lines for Phase 1's RED tests, validator, supersession pointer, portfolio, and roadmap changes.

That remaining budget could not satisfy the assigned Phase 1 behavior, so that attempt retained
no implementation. The later retained Phase 1 and Phase 2 records below supersede this historical
blocker; no runtime code, commit, push, PR, or review was created by the blocked attempt.

## Baseline Evidence

| Check | Exact result |
|---|---|
| `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` | Exit 0; 9 passed in 0.03s (coverage emitted pre-existing no-data warnings). |
| `python docs/tools/platform_portfolio/validate.py --root .` | Process exit 0 despite 2 CRITICAL `bad-ac-ev` violations: `ADAPTER-DATABASE-DOCKER:S62` and `CHG-FIRST-DATABASE-ADAPTER:S62`. |
| `git diff --check feature/refresh-platform-roadmap-after-stabilization...HEAD` | Exit 0; no tracked diff. |

## Phase 0 Retained Planning Baseline

- [x] 0.1 Limited PR 0 to the six planning artifacts: `exploration.md`, `proposal.md`, `specs/`, `design.md`, `tasks.md`, and `apply-progress.md`; no live documentation, validator, diagram, or runtime files changed.
- [x] 0.2 Recorded six planning artifacts totaling **387 authored lines** (≤400); `git diff --check` passed.
- [x] 0.3 PR 0 merged as #82 through `a44bae9dcdb59752016278a01cf226bed515078b` (`Merge pull request #82 from aparragithub/docs/refresh-platform-roadmap-after-stabilization`).

## Required Resolution / Precise Split

1. Put the six canonical planning artifacts on the tracker branch as a dedicated tracker-baseline
   change (382 authored additions; no implementation), then keep the tracker as the feature-chain
   aggregation branch.
2. Reforecast only Phase 1 against that updated tracker. Its child PR must contain the RED/GREEN
   validator tests and implementation, unchanged archive move plus supersession pointer, portfolio
   and stabilization-roadmap reconciliation, and this evidence update; it must remain at most 400
   authored additions plus deletions.
3. Do not begin Phase 2 or Phase 3. If the reforecasted Phase 1 child itself exceeds 400, split it
   before writing code rather than retaining an oversized diff.

## TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 1.1–1.5 | Not started — hard budget gate | Not started | Not started |

## Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command | Baseline only: `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 0, 9 passed. |
| Runtime harness | Baseline only: validator reported two CRITICAL S62 violations but exited 0. |
| Rollback boundary | This progress record only; no implementation retained. |

## Phase 1 Completion After PR 0 Retention

PR 0 merged on `a44bae9dcdb59752016278a01cf226bed515078b`; Phase 1 now targets
`feature/refresh-platform-roadmap-after-stabilization` and does not start PR 2 or PR 3.

- [x] 1.1 Archived unchanged `CHG-FIRST-DATABASE-ADAPTER`; resolved `S62` to its preserved
  real-Docker receipt; reconciled portfolio, roadmap, and exact inventory.
- [x] 1.2 Verified protected bytes, validator CLI exit semantics, exact inventory, and diff hygiene.

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `test_validate.py` | Unit/CLI | 9 passed | ✅ 5 contract tests failed: missing `file_sha256` | ✅ 14 passed | ✅ S62, inventory, stale roadmap, protected bytes, CLI exit | ✅ Pure repository helpers |
| 1.2 | `test_validate.py` | Unit/CLI | 9 passed | ✅ CRITICAL exit covered before gate change | ✅ 14 passed; CLI clean | ✅ valid/invalid repository fixtures | ➖ None needed |

| Evidence | Result |
|---|---|
| Focused test | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 0; 14 passed in 0.05s. |
| Runtime harness | `python docs/tools/platform_portfolio/validate.py --root .` — exit 0; `VALIDATOR: CLEAN — 0 violations`. |
| Protected bytes | Six archived adapter SHA-256 values match the pre-move manifest; source directory is absent. |
| Rollback boundary | Revert portfolio/roadmap/validator/test files and restore the adapter directory; no runtime, Unit 4, README, guide, Mermaid, SVG, or HTML change. |

PR 1 is forced chained, feature-branch-chain; its child branch targets the tracker. Exact temporary-index
diff count: **207 additions + 168 deletions = 375 changed lines**, within the 400 hard cap.
No commit, push, PR, review, Phase 2, or Phase 3 work occurred.

## Phase 2 Completion: Current Review-Facing Documentation

- [x] 2.1 Reconciled `README.md` and the Spanish current-implementation guide with the completed
  Docker PostgreSQL adapter, effective published layers/overrides, and materialized-state planning.
- [x] 2.2 Ran exact stale-claim, link, focused validator, and diff-hygiene checks. Commit remains
  deferred to the maintainer.

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 2.1 | `rg` surfaced the stale standalone-adapter, incomplete-published-layer, and no-operational-adapter claims before editing. | Exact stale-claim search exits 0 after the documentation update. | Added a concise Spanish source-of-truth section; no wholesale translation. |
| 2.2 | Pre-edit stale-claim count assertion exited 1 with four matches. | Link check, focused validator, and `git diff --check` exit 0. | None needed. |

| Evidence | Result |
|---|---|
| Focused test command | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 0; 14 passed in 0.04s (pre-existing coverage no-data warnings). |
| Exact stale-claim check | `rg` for the four removed stale strings in README/guide — exit 0; 0 matches. |
| Link check | Markdown-link `uv run python -c` check for README and guide — exit 0; `markdown links: OK`. |
| Runtime harness | N/A: documentation-only unit; no runtime or derived artifact boundary changed. |
| Rollback boundary | Revert only `README.md` and `docs/diagrams/odoo-forge-current-implementation-guide.md`; task/progress evidence can be reverted with the unit. |
| Review budget | Forced feature-branch-chain PR 2, base tracker at `ac4568d`; 75 additions + 34 deletions = 109 authored changed lines. |

No Mermaid, SVG, HTML, validator, portfolio, roadmap, runtime, or archive file changed. PR 3 remains
unstarted.

## Phase 3 Completion: Derived Views and Validator Follow-ups

Phase 3 RED/GREEN validator coverage covers normalized S62 containment, a missing
`openspec/changes` root, normalized top-level apply status, HTML language/current/target/link
ownership, stale claims, and fixed-renderer/derived-output inputs. The SVG was regenerated only
through the fixed renderer under the inherited Docker group and passed deterministic `--check`.
No SVG was hand-edited, no Unit 4 work was started, and no `verify-report.md` was created.

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 3.1–3.3 | `test_validate.py` | Unit/CLI | 14 passed | ✅ 5 contract failures; 14 passed | ✅ 19 passed | ✅ containment, missing-root, status, HTML/link/stale, renderer/output cases | ✅ Extracted pure repository helpers |
| 3.4–3.5 | `test_validate.py` | Integration/runtime | 19 passed | ✅ Renderer/input contract cases added first | ✅ validator CLI and renderer check pass | ✅ source, generated output, and CLI paths | ➖ None needed |

| Evidence | Result |
|---|---|
| RED | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 1; 5 new validator-contract failures, 14 passed. |
| GREEN / focused test | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` — exit 0; 19 passed in 0.21s. |
| Validator CLI / HTML, links, stale claims, inventory, protected bytes | `python docs/tools/platform_portfolio/validate.py --root .` — exit 0; `VALIDATOR: CLEAN — 0 violations`. |
| Stale claims | `rg` for the three stale current-state claims in Mermaid/HTML — exit 0; 0 matches. |
| Renderer runtime / source-output identity | `sg docker -c 'docs/diagrams/render-current-implementation.sh'` — exit 0; SVG generated only from Mermaid. `sg docker -c 'docs/diagrams/render-current-implementation.sh --check'` — exit 0; `odoo-forge-current-implementation.mmd.svg is current`. |
| Relevant full suite | `uv run pytest` — exit 0; 684 passed, 14 deselected in 13.99s. Not rerun after rendering because only the generated SVG changed. |
| Diff hygiene | `git diff --check 3baf2ffd458bf27090464436747e5024832c8714 --` — exit 0. |
| Rollback boundary | Revert Mermaid, generated SVG, bounded HTML, validator/tests, task/progress evidence; no unrelated runtime or Unit 4 behavior is removed. |

## Apply Handoff

- [x] 3.6 PR 1 #83 and PR 2 #84 merged; PR 3 tasks 3.1–3.5 are complete.
- [x] Native review `review-fd6c0911698f1f96` is approved with its persisted receipt.
- [x] Current apply status is complete. Next recommended phase: `sdd-verify`; it independently owns canonical `verify-report.md`.
