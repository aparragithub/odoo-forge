# Tasks: Refresh Platform Roadmap After Stabilization

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated authored changed lines | PR 0: 382–400; PR 1: 120–180; PR 2: 80–120; PR 3: 180–260 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 0 → PR 1 → PR 2 → PR 3 |
| Delivery strategy | force chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR/base | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 0 | Freeze six planning artifacts; record progress | PR 0; base tracker | `git diff --check` and line count | N/A: planning-only | Revert six planning artifacts |
| 1 | Archive stale change; reconcile authority, inventory, portfolio, roadmap | PR 1; base PR 0 | `git diff --check` plus inventory checks | `python docs/tools/platform_portfolio/validate.py` | Revert roadmap/portfolio; restore adapter directory |
| 2 | Reconcile README and Spanish guide | PR 2; base PR 1 branch | `git diff --check` plus stale-claim search | N/A: documentation-only; no derived artifact changes | Revert README and Spanish guide only |
| 3 | Reconcile Mermaid, SVG, HTML, validation, apply evidence | PR 3; base PR 2 | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` | `docs/diagrams/render-current-implementation.sh --check` | Revert Mermaid, SVG, HTML, validator/tests, apply evidence |

Generated-line accounting: count SVG in complete diff, byte identity, and evidence, not authored budget.

## Phase 0: Planning Baseline (PR 0)

- [x] 0.1 Changed only `exploration.md`, `proposal.md`, `specs/`, `design.md`, `tasks.md`, and `apply-progress.md`; excluded live docs, validator, and runtime files.
- [x] 0.2 Verified six planning artifacts total 387 authored lines (≤400); `git diff --check` passed and results are recorded in `apply-progress.md`.
- [x] 0.3 PR 0 `docs(platform): establish planning baseline` merged as #82 via merge `a44bae9`; PR 1 targeted the retained tracker baseline.

## Phase 1: Authority, Inventory, Portfolio, Roadmap (PR 1)

- [x] 1.1 Archive unchanged `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/`; update portfolio/roadmap authority, inventory, and S62 from HEAD; add RED/GREEN repository validator coverage.
- [x] 1.2 Verify protected bytes and exact active inventory; run the validator CLI and diff checks. Commit PR 1 as `docs(platform): reconcile authority and active inventory` is deferred to the maintainer.

## Phase 2: Current Review-Facing Documentation (PR 2)

- [x] 2.1 Reconcile `README.md` and `docs/diagrams/odoo-forge-current-implementation-guide.md` against Unit 1; preserve Spanish and label target/history content.
- [x] 2.2 Run `git diff --check` and exact stale-claim/link searches; commit Unit 2 as `docs(platform): reconcile current guidance` is deferred to the maintainer.

## Phase 3: Mermaid, SVG, HTML, Validation, and Evidence (PR 3)

- [x] 3.1 Update `docs/diagrams/odoo-forge-current-implementation.mmd` and bounded current-state regions of `docs/specs/platform/platform-architecture.html`; preserve Spanish, labels, links, and no implementation implications.
- [x] 3.2 Run `docs/diagrams/render-current-implementation.sh --check`; verify SVG derives from Mermaid and source/output bytes are deterministic.
- [x] 3.3 Add RED/GREEN validator tests for path allowlisting, HTML ownership/labels, links, stale claims, derived output, and the three PR1 follow-ups: normalize contradictory `apply-progress.md` top status, enforce normalized repository containment for S62 paths, and handle a missing `openspec/changes` root with documented exit semantics; extend `validate.py`.
- [x] 3.4 Run focused and full validator/tests, renderer, HTML/link/inventory/protected-byte checks; record apply evidence and outcomes in `apply-progress.md`. `sdd-apply` MUST NOT write `verify-report.md`.
- [x] 3.5 Preserve Mermaid+SVG+HTML source/derived coherence, generated SVG accounting, the ≤400 authored-line budget, and Unit 4 exclusion; commit PR 3 as `docs(platform): validate and publish reconciled views` is deferred to the maintainer.
- [x] 3.6 All apply tasks and approved review receipt `review-fd6c0911698f1f96` are complete; hand off to `sdd-verify`, which independently owns canonical `verify-report.md`; rollback PR 3, PR 2, PR 1, PR 0 if required.
