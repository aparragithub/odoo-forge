# Archive Report: Make Backend Planning Consume Materialized State

**Change**: make-backend-planning-consume-materialized-state  
**Status**: ✅ COMPLETE AND ARCHIVED  
**Archived to**: `openspec/changes/archive/2026-07-15-make-backend-planning-consume-materialized-state/`  
**Date**: 2026-07-15  
**Mode**: Hybrid (Engram + openspec)

---

## Delivery Traceability

| Item | Value |
|------|-------|
| Implementation PR | **#78** — merged to `main` as merge commit `c20727c3` (branch commit `45faafd`) |
| Archive PR | **#79** — merged to `main` as merge commit `f1af632` |
| Bounded review lineage | `review-8d424881b411639b` — terminal state **approved**, content-bound receipt validated at pre-commit and pre-push |
| Internal work structure | 3-work-unit feature-branch-chain (planned in `tasks.md`), collapsed into the single GitHub PR #78 at delivery |

> Note: the internal work-unit labels below ("Work Unit 1/2/3") are the planned
> implementation slices from `tasks.md`. They are NOT separate GitHub pull
> requests. GitHub PRs #75/#76/#77 belong to the unrelated database-adapter work
> and are not part of this change.

---

## Executive Summary

The `make-backend-planning-consume-materialized-state` change is complete, merged to main with green CI (merge commit `c20727c3`), and now archived. This change hardens backend mount selection by making it evidence-derived and fail-closed. `forge run` now requires complete, lock-consistent workspace evidence before executing; absent, incomplete, malformed, or commit-drifted evidence blocks execution before provider invocation with a single, actionable error. The pure core boundary remains untouched, and all identity commands (`status`, `stop`, `logs`, `exec`) stay workspace-independent and scan-free. Delivered as a single GitHub PR (#78), implemented internally as a 3-work-unit feature-branch-chain with strict TDD.

---

## What Shipped (implemented in PR #78, archived in PR #79)

### Capabilities Delivered

| Capability | Delivered in | Status |
|-----------|-----------|--------|
| Pure backend planning over validated mount-planning input | Work Unit 1 | Consumes validated evidence-derived mount view |
| Evidence-derived mount selection with fail-closed semantics | Work Unit 1–2 | No partial mounts; no static fallback |
| CLI boundary validation before provider invocation | Work Unit 2–3 | Single-cause errors for malformed/drifted evidence |
| Scan-free identity commands (status/stop/logs/exec) | Work Unit 3 | Unchanged behavior; workspace-independent |
| Materialized state as identity/commit evidence only | Work Unit 1–2 | Mount authority moved to planning view |

### Test & Lint Gates

| Gate | Result | Evidence |
|------|--------|----------|
| **Unit tests** | ✅ **599 passed, 6 deselected** | `uv run pytest` (integration tests deselected by default) |
| **Static checks** | ✅ **All passed** | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` |
| **Import-linter** | ✅ **6 contracts kept, 0 broken** | `uv run lint-imports` (core remains pure) |
| **CI (PR #78)** | ✅ **PASS** | `lint-and-test` green after the `ruff format` fix on `projection.py` |

### Specs Merged

| File | Action | Details |
|------|--------|---------|
| `openspec/specs/local-backend/spec.md` | **Updated** | Modified "plan_backend is a pure core boundary over validated mount-planning input" + "run/status/stop/logs/exec commands enforce a resilient boundary" requirements with new scenarios reflecting evidence-based mount validation and fail-closed semantics. |
| `openspec/specs/manifest/spec.md` | **Updated** | Modified "materialize_state is a pure core function over raw scan results" + "forge validate delegates all logic to the core" requirements to clarify state as identity/commit evidence only and workspace-scanning behavior in validate. |

### Artifacts Created

**Delta specs** merged into baselines:
- `openspec/changes/make-backend-planning-consume-materialized-state/specs/local-backend/spec.md` → merged into `openspec/specs/local-backend/spec.md`
- `openspec/changes/make-backend-planning-consume-materialized-state/specs/manifest/spec.md` → merged into `openspec/specs/manifest/spec.md`

---

## Internal Work-Unit Structure & Key Decisions

> Planned slices from `tasks.md`, all delivered together in PR #78. Line counts
> are the per-slice authored-work forecasts/evidence from `apply-progress.md`.

### Work Unit 1: Projection Validation & Mount-Planning View (Strict TDD)
- Added focused projection tests for missing/incoherent evidence, lock drift, and worktree precedence.
- Introduced `MountPlanningError` error family and the pure core mount-planning seam.
- Focused evidence: `tests/manifest/test_projection.py` — 30 passed.

**Key decision**: Mount authority moved from `MaterializedState` to a separate validated planning view; state remains identity/commit evidence only.

### Work Unit 2: Backend Planner Validation & Identity Seam (Strict TDD)
- Made `plan_backend` consume the validated mount-planning input and fail closed on incomplete/drifted evidence.
- Scan-free identity derivation for identity commands.
- Preserved a transitional `MaterializedState` compatibility branch pending the Work Unit 3 CLI migration.
- Focused evidence: `tests/backend/test_plan.py` + `test_status.py` — 35 passed.

**Key decisions**:
- Fail-closed: absent, incomplete, malformed, or drifted evidence blocks `run` before provider invocation.
- Evidence-backed mounts only: required repos must be present; optional/non-required roots MAY be absent.
- No partial mount sets or static fallback.
- Authorized compatibility correction (documented in `apply-progress.md`) for legacy `MaterializedState` callers.

### Work Unit 3: CLI Wiring & Fail-Closed Boundary (Strict TDD)
- Migrated `run` to load lock, scan/materialize evidence, build the mount-planning input, then plan and invoke provider.
- Removed the `MaterializedState` fallback from `plan_backend`.
- Made identity commands (`status`/`stop`/`logs`/`exec`) scan-free with no evidence dependency.
- Focused evidence: `tests/cli/test_backend.py` (128 passed) + adapter regression; cross-slice reruns (WU1: 30, WU2: 35 passed).

**Key decisions**:
- `run` MAY scan; `status`/`stop`/`logs`/`exec` MUST NOT scan.
- `BackendProvider` signatures unchanged.
- CLI renders single-cause errors for scan/evidence failures before provider calls.

### Post-Implementation Follow-ups (Documented in apply-progress.md)

1. **Authorized compatibility correction**: Added a transitional compatibility branch for legacy callers; atomically removed in Work Unit 3.
2. **Authorized final quality follow-up**: Updated integration test fixture, applied Ruff formatting, verified full gate.
3. **Authorized final security follow-up**: Hardened credential-bearing URL diagnostics in `MountPlanningError`; all constructions audited.
4. **Later structural-lock correction**: Added lock-structure validation to reject incomplete locks before mount planning.
5. **Final URL-identity follow-up**: Hardened `_repo_name` to sanitize authority-only URLs and malformed input.
6. **Post-merge format fix (PR #78)**: `ruff format` reformatted `src/odoo_forge/manifest/projection.py` (a manually wrapped `raise` on one line) to make CI's `ruff format --check` green.

---

## Verification & Compliance

> This change has **no** `verify-report.md` artifact. Verification evidence is the
> combination of `apply-progress.md` (per-slice TDD evidence and quality gates),
> green CI on PR #78, and the approved bounded-review receipt
> (`review-8d424881b411639b`).

### All Spec Requirements Met

Conformance evidence (`apply-progress.md` + merged spec scenarios) covers:
- `plan_backend` behavioral contract over validated mount-planning input
- `run`/`status`/`stop`/`logs`/`exec` resilient boundary
- `materialize_state` identity/commit evidence only
- `forge validate` workspace-scanning boundary
- Fail-closed blocking for absent/incomplete/malformed/drifted evidence
- Evidence-derived mount selection with no partial sets or fallback
- Scan-free identity operations
- `BackendProvider` port unchanged

### Purity Enforced

- Core imports zero filesystem-write or evidence-gathering symbols outside pure seams
- All mount authority decisions in the pure mount-planning seam and `plan_backend`
- Identity seam scan-free
- CLI orchestrates; core owns decision logic

### Tasks Completeness

- All 11 implementation tasks: ✅ complete (`apply-progress.md` evidence)
- Every numbered task in `tasks.md`: ✅ checked
- All follow-ups documented in `apply-progress.md` with exact evidence
- No stale unchecked boxes

### Security Compliance

- `MountPlanningError` diagnostics sanitized; no credential-bearing URLs in rendered messages
- Final URL-identity follow-up audited all `_repo_name` call sites; multi-case probe confirmed no secret leakage

---

## Cross-Session Pointers (Engram)

| Artifact | Type | ID | Purpose |
|----------|------|----|----|
| `sdd/make-backend-planning-consume-materialized-state/spec` | Decision | #7959 | Left planner signature open; behavioral contract preserved |
| `sdd/make-backend-planning-consume-materialized-state/design` | Architecture | #7972 | Corrected promoted worktree mount authority; fail-closed semantics |
| `sdd/make-backend-planning-consume-materialized-state/tasks` | Architecture | #7981 | 3-work-unit feature-branch-chain; strict TDD; per-slice verification |
| Session summaries | Session logs | #7952, #7960, #7982, #8282 | Phase continuity and status tracking |

---

## File Inventory

### Archived OpenSpec Artifacts
All artifacts moved from `openspec/changes/make-backend-planning-consume-materialized-state/` to `openspec/changes/archive/2026-07-15-make-backend-planning-consume-materialized-state/`:
- `proposal.md` — change intent, scope, and non-goals
- `exploration.md` — discovery and risk analysis
- `specs/local-backend/spec.md` — delta spec (merged to baseline)
- `specs/manifest/spec.md` — delta spec (merged to baseline)
- `design.md` — detailed architecture and decisions
- `tasks.md` — 3-work-unit chain with 11 tasks (all ✅)
- `apply-progress.md` — TDD cycle evidence, quality gates, follow-ups
- `archive-report.md` — this traceability document

### Updated Baseline Specs
- `openspec/specs/local-backend/spec.md` — updated with new requirement text and scenarios
- `openspec/specs/manifest/spec.md` — updated with new requirement text and scenarios

### Code (Merged to main @ `c20727c3` via PR #78)
- `src/odoo_forge/manifest/projection.py`, `src/odoo_forge/manifest/errors.py`, `tests/manifest/test_projection.py` (Work Unit 1)
- `src/odoo_forge/backend/plan.py`, `src/odoo_forge/backend/status.py`, `tests/backend/test_plan.py`, `tests/backend/test_status.py` (Work Unit 2)
- `src/odoo_forge_cli/main.py`, `tests/cli/test_backend.py`, `tests/adapters/test_docker_provider_integration.py` (Work Unit 3)

---

## Roadmap Status

`make-backend-planning-consume-materialized-state` marked COMPLETE and ARCHIVED:
- ✅ Feature branch merged to main via PR #78 (merge commit `c20727c3`)
- ✅ All 11 tasks complete with TDD evidence
- ✅ Quality gates green (599 tests, lints, type checks) and CI green on PR #78
- ✅ Specs synced into baseline (local-backend + manifest)
- ✅ Bounded review lineage `review-8d424881b411639b` approved (content-bound receipt validated)
- ✅ Archived via PR #79 (merge commit `f1af632`)

---

## Summary

✅ **The change is complete, verified, and archived.**

Backend mount planning now consumes validated workspace evidence and fails closed before provider invocation. The pure core boundary remains untouched. All identity commands stay scan-free. Delivered as a single GitHub PR (#78), archived via PR #79, with strict TDD and documented follow-ups. Specs merged into baseline; change artifacts moved to archive; ready for the next change.
