# Tasks: Make Backend Planning Consume Materialized State

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 270–360 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Estimated changed lines | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|---|
| 1 | 70–95 | PR 1 (base: feature/tracker → PR1); TDD the projection seam and error types first, then prove mount planning stays pure. | PR 1 | `uv run pytest tests/manifest/test_projection.py -q` | N/A (pure core) | `src/odoo_forge/manifest/projection.py`, `src/odoo_forge/manifest/errors.py` |
| 2 | 85–120 | PR 2 (base: PR1 → PR2); TDD planner/status identity separation and keep `BackendProvider` unchanged. | PR 2 | `uv run pytest tests/backend/test_plan.py tests/backend/test_status.py -q` | N/A (pure core) | `src/odoo_forge/backend/plan.py`, `src/odoo_forge/backend/status.py` |
| 3 | 115–145 | PR 3 (base: PR2 → PR3); TDD CLI fail-closed wiring, keep adapter tests scoped to unchanged `BackendPlan`/provider handoff, then capture final chain evidence. | PR 3 | `uv run pytest tests/cli/test_backend.py tests/adapters/test_docker_provider.py -q` | N/A (pytest covers the mocked CLI/core boundary; no separate live harness) | `src/odoo_forge_cli/main.py`, `tests/cli/test_backend.py`, `tests/adapters/test_docker_provider.py` |

## Phase 1: PR 1 — Projection / Error Seam

- [x] 1.1 RED: Add `tests/manifest/test_projection.py` cases for missing/incoherent evidence, lock drift, and worktree-vs-read-only precedence.
- [x] 1.2 GREEN: Implement `MountPlanningError` in `src/odoo_forge/manifest/errors.py` and pure `build_mount_planning_view` in `src/odoo_forge/manifest/projection.py`.
- [x] 1.3 Verify PR1 with `uv run pytest tests/manifest/test_projection.py -q`; record evidence only.

## Phase 2: PR 2 — Planner / Identity Separation

- [x] 2.1 RED: Add `tests/backend/test_plan.py` and `tests/backend/test_status.py` coverage for required/optional roots, canonical bind paths, determinism, and scan-free identity behavior.
- [x] 2.2 GREEN: Update `src/odoo_forge/backend/plan.py` to consume the validated mount view; retain the temporary legacy `MaterializedState` branch only until PR3 migrates every caller and removes it. Leave `BackendProvider` untouched.
- [x] 2.3 GREEN: Factor shared identity derivation in `src/odoo_forge/backend/status.py` so `status`/`stop`/`logs`/`exec` stay scan-free.
- [x] 2.4 Verify PR2 with `uv run pytest tests/backend/test_plan.py tests/backend/test_status.py -q`; keep rollback at the backend seam.

## Phase 3: PR 3 — CLI Wiring / Adapter Guard

- [x] 3.1 RED: Add `tests/cli/test_backend.py` cases for fail-closed `run`, one rendered error, no provider call on planning failure, and no-workspace-scan for `status`/`stop`/`logs`/`exec` at the CLI/core boundary.
- [x] 3.2 GREEN: Wire `src/odoo_forge_cli/main.py` to scan, materialize, build the planning view, and stop before provider invocation on any `MountPlanningError`; atomically migrate every legacy caller and remove PR2's `MaterializedState` compatibility branch in this same slice.
- [x] 3.3 RED/GREEN: Adjust `tests/adapters/test_docker_provider.py` only for unchanged `BackendPlan`/provider handoff; do not assert no-scan behavior here.
- [x] 3.4 Verify PR3 with the CLI/adapters pytest slice, then rerun PR1+PR2 focused commands on the feature-branch-chain base as final cross-chain evidence; no fourth implementation slice.
