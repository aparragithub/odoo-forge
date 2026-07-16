# Current Stabilization Roadmap

**Status:** reconciled with HEAD through `bbfd166` and the planning-only merge `a44bae9`.

`docs/specs/platform/portfolio.json` is the authoritative product, dependency, and evidence
record. This document is the review-facing sequence only; archived OpenSpec and dated roadmaps
remain historical evidence and are never rewritten.

## Current State

| Area | State | Evidence |
|---|---|---|
| Real-Docker baseline | Complete | Archived `stabilize-real-docker-baseline` verification report |
| Manifest layer and override semantics | Complete | Archived `decide-manifest-layer-override-semantics` change |
| Backend materialized-state planning | Complete | Archived `make-backend-planning-consume-materialized-state` change |
| First Docker PostgreSQL adapter | Complete and archived as superseded planning | `2026-07-15-CHG-DATABASE-ADAPTER-VERIFICATION-CLOSURE/verify-report.md` and `S62` |
| Unit 4 registry, Git, and workspace runtime-risk recheck | Separate future scope | Requires its own bounded SDD change |

`S62` resolves to the preserved real-Docker receipt in
[`CHG-FIRST-DATABASE-ADAPTER/apply-progress.md`](../../openspec/changes/archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/apply-progress.md).
The archived closure independently records five passing real-Docker adapter scenarios.

## Active OpenSpec Inventory

Every non-archived directory under `openspec/changes/` is listed here.

| Active change | Classification | Correct next step |
|---|---|---|
| [`refresh-platform-roadmap-after-stabilization`](../../openspec/changes/refresh-platform-roadmap-after-stabilization/proposal.md) | Active documentation reconciliation | Complete its chained authority, current-guidance, then derived-artifact slices. |
| [`sp-data-environments`](../../openspec/changes/sp-data-environments/proposal.md) | Blocked | Keep active; resume only when `WF-DATA-COPY` and `SP-CONTROL-PLANE-AUTHORITY` have accepted evidence. |

`sp-data-environments (blocked)` remains active; this change does not alter its prerequisites.

`CHG-FIRST-DATABASE-ADAPTER` is archived as superseded. Its preserved planning bytes and the
traceable closure pointer are in
[`archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/archive-report.md`](../../openspec/changes/archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/archive-report.md).

## Next Sequence

1. Finish the active roadmap-reconciliation change in reviewable chained slices.
2. Keep Unit 4 runtime-risk recheck independent from documentation reconciliation.
3. Do not start `sp-data-environments` implementation until all of its accepted handoffs exist.

## Explicit Non-Goals

- Rewriting archived OpenSpec, verification reports, receipts, or dated roadmaps.
- Treating achieved provider-neutral contracts as runtime integration.
- Folding Unit 4, runtime cutover, coordinated data copy, control-plane authority, or managed
  environments into the current documentation change.
- Starting `sp-data-environments` while it remains blocked.
