# Proposal: Make Backend Planning Consume Materialized State

## Intent

Backend mounts ignore workspace materialization, so `run` can start against historical static roots. Require complete, lock-consistent workspace evidence before backend execution.

## Goals

- Make mount selection evidence-derived and fail closed.
- Preserve pure core, thin CLI, and raw-fact scanner-adapter boundaries.
- Keep workspace-independent instance operations unchanged.

## Scope

### In Scope
- Derive a mount-planning view from scan/materialization evidence and the lock; do not enrich `MaterializedState` with filesystem authority.
- Block `run` before provider invocation for absent, incomplete, incoherent, or commit-drifted evidence; never create partial mounts or use static fallback.
- Retain state-independent `status`, `stop`, `logs`, and `exec`.

### Non-Goals
- Changes to `BackendProvider`, Docker lifecycle/runtime behavior, `lock`, `project`, or `unlock`.
- `CHG-FIRST-DATABASE-ADAPTER`, `sp-data-environments`, runtime database cutover, and portfolio-status changes.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `local-backend`: `run` mount planning becomes evidence- and lock-gated; identity commands remain state-independent.
- `manifest`: scan/materialization evidence is used to derive a mount-planning view without changing `MaterializedState`'s identity/commit role.

## User-visible Behavior

`forge run` MUST stop before provisioning with an actionable, single-cause error for missing, incomplete, malformed, or `project.lock`-mismatched evidence. It MUST not mount a subset or historical roots. Malformed paths remain scanner/projection `ScanError`s. Identity commands retain their no-scan behavior.

## Architectural Direction

The scanner adapter returns raw `ScannedRepo` facts. Pure core validates them against projection/lock expectations and derives the planning view; `plan_backend` produces `BackendPlan`. The CLI orchestrates and renders failures once. `BackendProvider` receives only `BackendPlan`; an indispensable port change blocks this proposal pending an explicit decision.

## Compatibility and Migration

No persisted `MaterializedState` schema or provider contract change is planned. Operators must materialize a complete, matching workspace before `run`; this intentional compatibility break has no fallback. `docs/specs/platform/portfolio.json` remains product/dependency authority; the roadmap only bounds Unit 3.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/backend/plan.py` | Modified | Evidence-derived mounts |
| `src/odoo_forge/manifest/` | Modified | Pure view/validation |
| `src/odoo_forge_cli/main.py` | Modified | `run` boundary |

## Risks and Rollback

| Risk | Mitigation |
|---|---|
| Valid workspace rejected | Deterministic evidence/lock diagnostics |
| Identity regression | Preserve empty-state identity path |

Rollback by reverting planner, validation, and CLI wiring together to the prior release; never add a runtime silent fallback. No data migration or provider rollback is required.

## Delivery and Acceptance Outcomes

- [ ] `run` reaches the provider only with complete, coherent, lock-matching evidence.
- [ ] Missing, incomplete, malformed, and drifted evidence blocks `run` without partial mounts.
- [ ] Identity commands remain workspace-independent; `BackendProvider` is unchanged.
- [ ] Delivery will be force-chained under a 400 changed-line review budget; slices are deferred to planning.
