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
| 3 | Reconcile Mermaid, SVG, HTML, validation, evidence | PR 3; base PR 2 | `uv run pytest docs/tools/platform_portfolio/test_validate.py -q` | `docs/diagrams/render-current-implementation.sh --check` | Revert Mermaid, SVG, HTML, validator/tests, evidence |

Generated-line accounting: count SVG in complete diff, byte identity, and evidence, not authored budget.

## Phase 0: Planning Baseline (PR 0)

- [ ] 0.1 Change only `exploration.md`, `proposal.md`, `specs/`, `design.md`, `tasks.md`, and `apply-progress.md`; exclude live docs, validator, and runtime files.
- [ ] 0.2 Verify six planning artifacts remain ≤400 authored lines; run `git diff --check` and record results in `apply-progress.md`.
- [ ] 0.3 Commit PR 0 as `docs(platform): establish planning baseline`; PR 1 targets PR 0.

## Phase 1: Authority, Inventory, Portfolio, Roadmap (PR 1)

- [x] 1.1 Archive unchanged `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/`; update portfolio/roadmap authority, inventory, and S62 from HEAD; add RED/GREEN repository validator coverage.
- [x] 1.2 Verify protected bytes and exact active inventory; run the validator CLI and diff checks. Commit PR 1 as `docs(platform): reconcile authority and active inventory` is deferred to the maintainer.

## Phase 2: Current Review-Facing Documentation (PR 2)

- [x] 2.1 Reconcile `README.md` and `docs/diagrams/odoo-forge-current-implementation-guide.md` against Unit 1; preserve Spanish and label target/history content.
- [x] 2.2 Run `git diff --check` and exact stale-claim/link searches; commit Unit 2 as `docs(platform): reconcile current guidance` is deferred to the maintainer.

## Phase 3: Mermaid, SVG, HTML, Validation, and Evidence (PR 3)

- [ ] 3.1 Update `docs/diagrams/odoo-forge-current-implementation.mmd` and bounded current-state regions of `docs/specs/platform/platform-architecture.html`; preserve Spanish, labels, links, and no implementation implications.
- [ ] 3.2 Run `docs/diagrams/render-current-implementation.sh --check`; verify SVG derives from Mermaid and source/output bytes are deterministic.
- [ ] 3.3 Add RED/GREEN validator tests for path allowlisting, HTML ownership/labels, links, stale claims, and derived output; extend `validate.py`.
- [ ] 3.4 Run validator, tests, renderer, HTML/link/inventory/protected-byte checks; write canonical `verify-report.md` and native evidence.
- [ ] 3.5 Commit PR 3 as `docs(platform): validate and publish reconciled views`; rollback PR 3, then PR 2, PR 1, PR 0.
