# Archive Report: Make Backend Planning Consume Materialized State

**Change**: make-backend-planning-consume-materialized-state  
**Status**: ✅ COMPLETE AND ARCHIVED  
**Archived to**: `openspec/changes/archive/2026-07-15-make-backend-planning-consume-materialized-state/`  
**Date**: 2026-07-15  
**Mode**: Hybrid (Engram + openspec)

---

## Executive Summary

The `make-backend-planning-consume-materialized-state` change is complete, merged to main with green CI (commit c20727c3), verified PASS, and now archived. This change hardens backend mount selection by making it evidence-derived and fail-closed. `forge run` now requires complete, lock-consistent workspace evidence before executing; absent, incomplete, malformed, or commit-drifted evidence blocks execution before provider invocation with a single, actionable error. The pure core boundary remains untouched, and all identity commands (`status`, `stop`, `logs`, `exec`) stay workspace-independent and scan-free. Delivered in a 3-PR feature-branch chain with strict TDD and comprehensive verification.

---

## What Shipped (3-PR Feature-Branch Chain: PR #75, #76, #77)

### Capabilities Delivered

| Capability | Delivered | Status |
|-----------|-----------|--------|
| Pure backend planning over validated mount-planning input | ✅ PR #75 | Consumes validated evidence-derived mount view |
| Evidence-derived mount selection with fail-closed semantics | ✅ PR #75–#76 | No partial mounts; no static fallback |
| CLI boundary validation before provider invocation | ✅ PR #76–#77 | Single-cause errors for malformed/drifted evidence |
| Scan-free identity commands (status/stop/logs/exec) | ✅ PR #77 | Unchanged behavior; workspace-independent |
| Materialized state as identity/commit evidence only | ✅ PR #75–#76 | Mount authority moved to planning view |

### Test & Lint Gates

| Gate | Result | Evidence |
|------|--------|----------|
| **Unit tests** | ✅ **599 passed, 6 deselected** | `uv run pytest` (integration tests deselected by default) |
| **Static checks** | ✅ **All passed** | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` |
| **Import-linter** | ✅ **6 contracts kept, 0 broken** | `uv run lint-imports` (core remains pure) |
| **Final quality gate** | ✅ **PASS** | 599 passed, all lints/formats green, no whitespace errors |

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

## PR Chain Structure & Key Decisions

### PR #75: Projection Validation & Mount-Planning View (Strict TDD)
- Added focused projection tests for missing/incoherent evidence, lock drift, and worktree precedence.
- Introduced `MountPlanningError` error family and `build_mount_planning_view` pure core seam.
- Tests: 26 baseline → 30 passed; 3 new tests added.
- Changed lines: ~170 (within budget)

**Key decision**: Mount authority moved from `MaterializedState` to a separate validated planning view; state remains identity/commit evidence only.

### PR #76: Backend Planner Validation & Identity Seam (Strict TDD)
- Made `plan_backend` consume `MountPlanningView` and fail closed on incomplete/drifted evidence.
- Added `derive_instance_ref` for scan-free identity derivation.
- Preserved transitional `MaterializedState` compatibility branch pending PR #77 CLI migration.
- Tests: 35 backend + 36 plan tests; full quality gate pass.
- Changed lines: 341 authored (169 additions, 172 deletions) within 400-line budget.

**Key decisions**:
- Fail-closed: absent, incomplete, malformed, or drifted evidence blocks `run` before provider invocation.
- Evidence-backed mounts only: required repos must be present; optional/non-required roots MAY be absent.
- No partial mount sets or static fallback.
- Authorized PR2 compatibility correction (documented in apply-progress.md) for legacy `MaterializedState` callers.

### PR #77: CLI Wiring & Fail-Closed Boundary (Strict TDD)
- Migrated `run` to load lock, scan/materialize evidence, build `MountPlanningView`, then plan and invoke provider.
- Removed `MaterializedState` fallback from `plan_backend`.
- Made identity commands (`status`/`stop`/`logs`/`exec`) scan-free with no evidence dependency.
- Tests: 128 CLI + 92 adapter regression tests pass; cross-chain verification (PR1: 30, PR2: 35 passed).
- Changed lines: ~385 (within budget)

**Key decisions**:
- `run` MAY scan; `status`/`stop`/`logs`/`exec` MUST NOT scan.
- `BackendProvider` signatures unchanged.
- CLI renders single-cause errors for scan/evidence failures before provider calls.

### Post-Implementation Follow-ups (Documented in apply-progress.md)

1. **Authorized PR2 Compatibility Correction**: Added transitional compatibility branch for legacy callers; atomically removed in PR3.
2. **Authorized Final Quality Follow-up**: Updated integration test fixture, applied Ruff formatting, verified full gate.
3. **Authorized Final Security Follow-up**: Hardened credential-bearing URL diagnostics in `MountPlanningError`; all 12 constructions audited.
4. **Later Structural-Lock Correction**: Added `_validate_lock_structure` to reject incomplete locks before mount planning.
5. **User-Authorized Final URL-Identity Follow-up**: Hardened `_repo_name` to sanitize authority-only URLs and malformed input.

---

## Key Design Decisions (Merged with Evidence)

| Decision | Evidence | Status |
|----------|----------|--------|
| **Mount authority moved to planning view** | Pure `build_mount_planning_view` validates evidence; `MaterializedState` remains identity/commit only | PASS — test_build_mount_planning_view_* |
| **Fail-closed `run` for incomplete/drifted evidence** | Missing lock, incomplete roots, malformed scan, stale commit all block before provider call | PASS — test_run_fails_closed_* + 4 CLI failure cases |
| **Evidence-backed mounts only** | Required repos must be present; optional/non-required MAY be absent; unexpected rejected | PASS — test_plan_backend_optional_roots_absent |
| **No partial mount sets or fallback** | `run` exits non-zero before provider invocation; no half-provisioned state | PASS — test_run_fails_closed_before_provider |
| **Scan-free identity commands** | `status`/`stop`/`logs`/`exec` use instance identity only; no workspace scan | PASS — test_status_scan_error_parametrization (5 commands) |
| **Single-cause CLI errors** | Malformed scan, incomplete evidence, commit drift each render once before provider | PASS — test_scan_error_from_corrupted_checkout_exits_clean_one_error |
| **BackendProvider unchanged** | No signature changes; no new ports; adapter tests confirm existing handoff | PASS — test_adapter_regression_suite (92 passed) |

---

## Verification & Compliance

### All Spec Requirements Met

✅ Comprehensive conformance matrix in verify-report covers:
- `plan_backend` behavioral contract over validated mount-planning input (11 scenarios)
- `run`/`status`/`stop`/`logs`/`exec` resilient boundary (8 scenarios)
- `materialize_state` identity/commit evidence only (5 scenarios)
- `forge validate` workspace-scanning boundary (4 scenarios)
- Fail-closed blocking for absent/incomplete/malformed/drifted evidence
- Evidence-derived mount selection with no partial sets or fallback
- Scan-free identity operations
- BackendProvider port unchanged

### Purity Enforced

- Core imports zero filesystem-write or evidence-gathering symbols outside pure seams
- All mount authority decisions in `build_mount_planning_view` and `plan_backend`
- Identity seam (`derive_instance_ref`) scan-free
- CLI orchestrates; core owns decision logic

### Tasks Completeness

- All 11 implementation tasks: ✅ complete (apply-progress.md evidence)
- Every numbered task in tasks.md: ✅ checked
- All follow-ups documented in apply-progress.md with exact evidence
- No stale unchecked boxes

### Security Compliance

- `MountPlanningError` diagnostics sanitized; no credential-bearing URLs in rendered messages
- Proof: Final URL-identity follow-up audited all 13 `_repo_name` call sites
- Nine-case `_repo_name` probe confirmed no secret leakage

---

## Cross-Session Pointers (Engram)

| Artifact | Type | ID | Purpose |
|----------|------|----|----|
| `sdd/make-backend-planning-consume-materialized-state/spec` | Decision | #7959 | Left planner signature open; behavioral contract preserved |
| `sdd/make-backend-planning-consume-materialized-state/design` | Architecture | #7972 | Corrected promoted worktree mount authority; fail-closed semantics |
| `sdd/make-backend-planning-consume-materialized-state/tasks` | Architecture | #7981 | 3-PR feature-branch-chain; strict TDD; per-PR verification |
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
- `tasks.md` — 3-PR chain with 11 tasks (all ✅)
- `apply-progress.md` — TDD cycle evidence, quality gates, follow-ups
- `archive-report.md` — this traceability document

### Updated Baseline Specs
- `openspec/specs/local-backend/spec.md` — updated with new requirement text and scenarios
- `openspec/specs/manifest/spec.md` — updated with new requirement text and scenarios

### Code (Merged to main @ c20727c3)
All changes committed in 3-PR feature-branch chain:
- PR #75: Projection validation (`src/odoo_forge/manifest/projection.py`, `errors.py`, `tests/manifest/test_projection.py`)
- PR #76: Backend planning (`src/odoo_forge/backend/plan.py`, `status.py`, `tests/backend/test_plan.py`, `test_status.py`)
- PR #77: CLI wiring (`src/odoo_forge_cli/main.py`, `tests/cli/test_backend.py`, integration test fixtures)

---

## Roadmap Status

Roadmap updated to mark `make-backend-planning-consume-materialized-state` COMPLETE and ARCHIVED with:
- ✅ Feature branch chain merged to main (merge commit c20727c3)
- ✅ All 11 tasks complete with TDD evidence
- ✅ Quality gates green (599 tests, lints, type checks)
- ✅ Specs synced into baseline (local-backend + manifest)
- ✅ PR review lineage approved (content-bound receipt validated)
- ✅ Archive report with observation IDs for traceability

---

## Summary

✅ **The change is complete, verified, and archived.**

Backend mount planning now consumes validated workspace evidence and fails closed before provider invocation. The pure core boundary remains untouched. All identity commands stay scan-free. Delivered in a 3-PR feature-branch chain with strict TDD, comprehensive verification, and documented follow-ups. Specs merged into baseline; change artifacts moved to archive; ready for the next change.
