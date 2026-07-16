# Apply Progress: Make Backend Planning Consume Materialized State

## PR 1 — Projection / Error Seam

**Mode:** Strict TDD

### Completed Tasks

- [x] 1.1 RED: Add focused projection tests for missing/incoherent evidence, lock drift, and worktree precedence.
- [x] 1.2 GREEN: Add `MountPlanningError`, mount-planning view models, and pure evidence validation.
- [x] 1.3 Verify the focused projection test slice.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/manifest/test_projection.py` | Unit | 26 passed | `ImportError: MountPlanningError` (1 collection error) | 29 passed | Missing evidence, unexpected/drifted evidence, and promoted-worktree precedence | None needed |
| 1.2 | `tests/manifest/test_projection.py` | Unit | 26 passed | Tests written before production symbols existed | 29 passed | Valid and invalid evidence paths exercise distinct selection/rejection branches | Duplicate identity/container-path guards added; 29 passed |
| 1.3 | `tests/manifest/test_projection.py` | Unit | N/A — verification-only task | N/A — no production behavior added | 30 passed | N/A — covered by tasks 1.1–1.2 | None needed |

### Test Summary

- Total tests written: 3
- Total tests passing: 30
- Layers used: Unit (3)
- Approval tests: None — no refactoring task
- Pure functions created: 1 (`build_mount_planning_view`)

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 30 passed in 0.37s |
| Runtime harness command/scenario and exact result | N/A — this PR is a pure manifest-core projection seam with no runtime boundary. |
| Rollback boundary | Revert `src/odoo_forge/manifest/projection.py`, `src/odoo_forge/manifest/errors.py`, and their focused tests; this removes only PR1 evidence validation/view behavior. |

### Independent Verification Follow-up

- `uv run ruff check src/odoo_forge/manifest/errors.py src/odoo_forge/manifest/projection.py tests/manifest/test_projection.py` — exit 0, all checks passed.
- `uv run mypy src/odoo_forge/manifest/errors.py src/odoo_forge/manifest/projection.py tests/manifest/test_projection.py` — exit 0, no issues found in 3 source files.
- `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 30 passed in 0.37s.
- Follow-up changes were mechanical formatting, removal of a stray useless test expression, and evidence refresh only; no feature behavior changed.

### PR Boundary

- Mode: feature-branch-chain, PR 1 slice.
- Start: raw scan facts, lock, and materialized identity state.
- End: validated deterministic `MountPlanningView` and typed mount-planning error.
- Excluded: backend planner, provider, CLI, `CHG-FIRST-DATABASE-ADAPTER`, and `sp-data-environments`.

## PR 2 — Planner / Identity Separation

**Mode:** Strict TDD

### Completed Tasks

- [x] 2.1 RED: Add backend-plan/status coverage for validated per-repository mounts, canonical targets, determinism, and scan-free identity.
- [x] 2.2 GREEN: Make `plan_backend` consume `MountPlanningView`, retain a PR2-only legacy `MaterializedState` branch pending PR3 caller migration/removal, and preserve the `BackendProvider` port.
- [x] 2.3 GREEN: Add shared pure `derive_instance_ref` identity derivation.
- [x] 2.4 Verify the focused planner/status slice and targeted static checks.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 2.1 | `tests/backend/test_plan.py`, `tests/backend/test_status.py` | Unit | `uv run pytest tests/backend/test_plan.py tests/backend/test_status.py -q` — 35 passed | Added canonical per-repo bind and absent `derive_instance_ref` assertions first; 4 failed, 31 passed | 35 passed | Read-only and promoted-worktree mounts; default and sanitized-instance identities | Shared test view replaces obsolete state fixture; 35 passed |
| 2.2 | `tests/backend/test_plan.py` | Unit | 35 passed | Task 2.1 canonical-mount assertion failed against fixed root mounts; the initial compatibility-seam test then failed with `AttributeError` | Initial GREEN (later corrected): 36 passed with legacy state rejected | Historical initial behavior covered two distinct source/target/read-only bindings, legacy state rejection, and repeated-plan equality; the current-final behavior is recorded in the authorized correction below | Initial static-root removal was retained for `MountPlanningView`; the legacy rejection was superseded by the transitional compatibility correction; 36 passed |
| 2.3 | `tests/backend/test_status.py` | Unit | 35 passed | Task 2.1 identity assertion referenced missing `derive_instance_ref` | 35 passed | Default and sanitized instance names yield concrete, deterministic refs | Moved shared sanitization/identity logic to status without changing provider contract; 35 passed |
| 2.4 | `tests/backend/test_plan.py`, `tests/backend/test_status.py` | Unit | N/A — verification-only task | N/A — no new production behavior | 35 passed | N/A — covered by 2.1–2.3 | Targeted Ruff and mypy both pass |

### Test Summary

- Total tests written: 4 behavioral cases (canonical per-repository binds; transitional legacy compatibility; default identity; sanitized identity)
- Total tests passing: 36
- Layers used: Unit (36)
- Approval tests: None — behavior changed from static roots to validated per-repository evidence.
- Pure functions created: 1 (`derive_instance_ref`; `sanitize_name` moved to the shared pure identity module)

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/backend/test_plan.py tests/backend/test_status.py -q` — exit 0, 36 passed in 0.43s |
| Runtime harness command/scenario and exact result | N/A — PR2 is pure backend-core planning/identity logic; CLI/provider runtime wiring is intentionally PR3-only. |
| Rollback boundary | Revert `src/odoo_forge/backend/plan.py`, `src/odoo_forge/backend/status.py`, `tests/backend/test_plan.py`, and `tests/backend/test_status.py`; this removes only validated-view mount consumption and scan-free identity derivation. |

### Static Verification

- `uv run ruff check src/odoo_forge/backend/plan.py src/odoo_forge/backend/status.py tests/backend/test_plan.py tests/backend/test_status.py` — exit 0, all checks passed.
- `uv run mypy src/odoo_forge/backend/plan.py src/odoo_forge/backend/status.py tests/backend/test_plan.py tests/backend/test_status.py` — exit 0, no issues found in 4 source files.
- `uv run mypy src/odoo_forge_cli/main.py` — exit 0, no issues found in 1 source file; the typed compatibility seam preserves legacy callers until PR3 atomically migrates them and removes the branch.

### PR Boundary

- Mode: feature-branch-chain, PR 2 slice; base is PR1 and target is the immediate PR1 branch.
- Start: validated `MountPlanningView` from PR1.
- End: per-repository backend binds and pure instance identity available for PR3 CLI wiring.
- Excluded: CLI, providers/adapters, lock/project/unlock, protected changes, and all PR3 tests.
- Current-final review boundary: 169 additions + 172 deletions = 341 authored changed lines against an 85–120 forecast; +221 over forecast, still within the 400-line budget.

## Authorized PR2 Compatibility Correction (Current Final Behavior)

- The task 2.2 RED and initial GREEN entries above are historical TDD facts. Their legacy-rejection behavior was superseded by this correction and is not the final PR2 behavior.
- Frozen lineage/findings: `review-76bd517fa5e545a8` — R2-001, R3-001, R4-001.
- `plan_backend` uses evidence-derived mounts for `MountPlanningView` and explicitly preserves pre-PR3 static-root behavior for legacy `MaterializedState` callers as a transitional compatibility branch.
- PR3 MUST atomically migrate every CLI caller to `MountPlanningView` and remove this compatibility branch in the same slice; final verification MUST reject a surviving branch.
### TDD Cycle Evidence
| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
| PR2 correction | `tests/backend/test_plan.py` | Unit | 36 passed | Legacy caller test failed with `MountPlanningError` | 36 passed | Legacy static roots and evidence-derived per-repo mounts | Formatting only; focused tests remain green |
### Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/backend/test_plan.py tests/backend/test_status.py -q` — exit 0, 36 passed in 0.39s |
| Runtime harness command/scenario and exact result | `uv run pytest tests/cli/test_backend.py -q` — exit 0, 32 passed in 1.41s; existing `run`/`status`/`stop`/`logs`/`exec` callers cross the planner boundary. |
| Rollback boundary | Revert the compatibility branch in `src/odoo_forge/backend/plan.py` and its regression in `tests/backend/test_plan.py`; no provider or CLI wiring changes are included. |
```json
{"schema":"gentle-ai.remediation-result/v1","lineage_id":"review-76bd517fa5e545a8","generation":1,"fix_batch":1,"failed_evidence_revision":"sha256:77dd8883c45e92d2eb21a39d73db765b70e5ee679b3e6c0799eeeaf66dd7f8e4","findings":["R2-001","R3-001","R4-001"],"status":"corrected"}
```
```json
{"schema":"gentle-ai.remediation-evidence/v1","lineage_id":"review-76bd517fa5e545a8","generation":1,"fix_batch":1,"failed_evidence_revision":"sha256:77dd8883c45e92d2eb21a39d73db765b70e5ee679b3e6c0799eeeaf66dd7f8e4","focused_test":"36 passed","cli_regression":"32 passed","static_checks":"ruff and mypy passed"}
```

## PR 3 — CLI Wiring / Adapter Guard

**Mode:** Strict TDD

### Completed Tasks

- [x] 3.1 RED: Add CLI regressions for missing lock, incomplete evidence, malformed scan evidence, and stale commit evidence; each fails closed with one rendered error and no provider call.
- [x] 3.2 GREEN: Make `run` load the lock, scan/materialize evidence, build `MountPlanningView`, then plan and invoke the provider; migrate identity commands to `derive_instance_ref` and remove the `MaterializedState` fallback from `plan_backend`.
- [x] 3.3 RED/GREEN: Confirm the unchanged `BackendPlan` → `BackendProvider` adapter handoff with the existing focused adapter regression suite; no adapter no-scan assertion was added.
- [x] 3.4 Verify PR3 and rerun the PR1 and PR2 focused slices as final cross-chain evidence.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 3.1 | `tests/cli/test_backend.py` | CLI integration | `uv run pytest tests/cli/test_backend.py tests/adapters/test_docker_provider.py -q` — 124 passed | Added missing-lock, incomplete, malformed, and stale-evidence cases; 3 failed because the provider was reached | `uv run pytest tests/cli/test_backend.py -q` — 36 passed | Four distinct invalid-evidence paths plus existing identity no-scan parametrization | Test fixture now writes a matching lock and complete raw evidence by default; 36 passed |
| 3.2 | `tests/cli/test_backend.py`, `tests/backend/test_plan.py` | CLI integration / unit | 124 passed | Task 3.1 failures preceded the CLI wiring; legacy-state test was removed only after every CLI identity caller used the pure seam | 36 CLI passed; 35 backend planner/status passed | Successful evidence-backed provisioning, four fail-closed modes, and four scan-free identity commands | Removed the transitional union/branch and simplified identity callers; focused tests remain green |
| 3.3 | `tests/adapters/test_docker_provider.py` | Adapter regression | 124 passed | N/A — the task requires no adapter behavior change; existing handoff regressions are the required guard | `uv run pytest tests/adapters/test_docker_provider.py -q` — 92 passed | Existing adapter cases exercise successful plan consumption and failure behavior without workspace assumptions | None needed — `BackendProvider` and adapter source are unchanged |
| 3.4 | PR3, PR1, PR2 focused slices | Integration / unit | N/A — verification-only task | N/A — no production behavior added | PR3 128 passed; PR1 30 passed; PR2 35 passed | N/A — covered by tasks 3.1–3.3 | Targeted Ruff/mypy and `git diff --check` pass |

### Test Summary

- Total tests written: 4 invalid-evidence CLI cases.
- Total tests passing: PR3 128; PR1 30; PR2 35.
- Layers used: CLI integration (4 cases), unit and adapter regression (existing focused coverage).
- Approval tests: None — PR3 removes an explicitly transitional compatibility branch.
- Pure functions created: None — `derive_instance_ref` from PR2 is consumed as the identity seam.

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/cli/test_backend.py tests/adapters/test_docker_provider.py -q` — exit 0, 128 passed in 3.44s. |
| Runtime harness command/scenario and exact result | N/A — the focused pytest slice exercises the CLI/core/provider boundary with fakes; a live Docker runtime is outside this slice and no runtime boundary changed in the adapter. |
| Rollback boundary | Revert `src/odoo_forge_cli/main.py`, `src/odoo_forge/backend/plan.py`, `tests/cli/test_backend.py`, and the PR3 test adjustment in `tests/backend/test_plan.py`; this restores only the prior CLI/planner transition. Do not revert PR1/PR2 projection/identity seams independently. |

### Historical Targeted and Cross-Chain Verification

These results were focused slice evidence captured during implementation. They did not establish the full configured quality gate; that gate was completed only in the final quality follow-up below.

- `uv run ruff check src/odoo_forge/backend/plan.py src/odoo_forge_cli/main.py tests/backend/test_plan.py tests/cli/test_backend.py tests/adapters/test_docker_provider.py` — exit 0, all checks passed.
- `uv run mypy src/odoo_forge/backend/plan.py src/odoo_forge_cli/main.py tests/backend/test_plan.py tests/cli/test_backend.py tests/adapters/test_docker_provider.py` — exit 0, no issues found in 5 source files.
- `git diff --check` — exit 0, no whitespace errors.
- `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 30 passed in 0.38s (PR1 cross-chain evidence).
- `uv run pytest tests/backend/test_plan.py tests/backend/test_status.py -q` — exit 0, 35 passed in 0.51s (PR2 cross-chain evidence).

### PR Boundary

- Mode: feature-branch-chain, PR 3 final slice; base is the immediate PR2 branch and this child must not target `main` directly.
- Start: PR2's validated mount-planning view and pure identity seam.
- End: fail-closed `run` orchestration with no static/historical planner fallback; identity commands stay scan-free.
- Excluded: `BackendProvider` signatures, Docker adapter behavior, `lock`, `project`, `unlock`, protected changes, and final SDD verify/archive phases.
- Review impact: within the 115–145-line PR3 forecast for authored slice work; no `size:exception` required.

## Authorized Final Quality Follow-up

- Updated `tests/adapters/test_docker_provider_integration.py` to construct the minimal valid `MountPlanningView(mounts=())` required by `plan_backend`. The real-Docker lifecycle behavior is unchanged, and no `MaterializedState` compatibility was reintroduced.
- Applied Ruff formatting only to `src/odoo_forge/backend/plan.py`, `tests/cli/test_backend.py`, and the edited integration test. Ruff reformatted the first two files and left the integration test unchanged.
- Full configured quality gate, run after the follow-up:
  - `uv run pytest` — exit 0, 585 passed, 6 deselected in 4.25s; integration tests remained deselected by default.
  - `uv run lint-imports` — exit 0, 6 contracts kept, 0 broken.
  - `uv run ruff check .` — exit 0, all checks passed.
  - `uv run ruff format --check .` — exit 0, 113 files already formatted.
  - `uv run mypy` — exit 0, no issues found in 110 source files.
  - `git diff --check` — exit 0, no output.
- Live Docker evidence: `uv run pytest -m integration -rs tests/adapters/test_docker_provider_integration.py::test_run_status_stop_round_trip_against_real_daemon` — exit 0, 1 skipped in 0.46s because the Docker daemon was unreachable; no Docker resources were created.
- Behavior impact: none in production. This follow-up updates one integration-test fixture call, applies formatting, and corrects evidence chronology.

## Authorized Final Security Follow-up

- Audited all 12 `MountPlanningError` constructions in `src/odoo_forge/manifest/projection.py`. Nine were static or already used the credential-safe `_repo_name(...)` convention; the three remaining raw URL diagnostics were duplicate scanned evidence, duplicate materialized evidence, and materialized commit drift.
- Replaced only those three raw URL interpolations with `_repo_name(...)`, preserving the layer and repository basename in each diagnostic. No architecture, planner/CLI/provider contract, or non-diagnostic behavior changed.
- Added credential-bearing URL regressions for all three paths; duplicate scanned evidence covers both read-only and worktree source kinds.

### TDD Cycle Evidence

| Test File | Layer | RED | GREEN |
|---|---|---|---|
| `tests/manifest/test_projection.py` | Unit | `uv run pytest tests/manifest/test_projection.py -q` — exit 1, 4 failed and 30 passed; every new assertion observed the leaked username/token/full URL | `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 34 passed in 0.43s |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 34 passed in 0.43s. |
| Runtime harness command/scenario and exact result | N/A — this follow-up changes pure diagnostic rendering only; the focused unit tests invoke every corrected error path directly. |
| Rollback boundary | Revert the three `_repo_name(...)` substitutions in `src/odoo_forge/manifest/projection.py`, their regressions in `tests/manifest/test_projection.py`, and this section; no other behavior belongs to this follow-up. |

### Final Quality Gate

- `uv run pytest` — exit 0, 589 passed, 6 deselected in 4.51s.
- `uv run lint-imports` — exit 0, 6 contracts kept, 0 broken.
- `uv run ruff check .` — exit 0, all checks passed.
- `uv run ruff format --check .` — exit 0, 113 files already formatted.
- `uv run mypy` — exit 0, no issues found in 110 source files.
- `git diff --check` — exit 0, no output.
- Remaining raw URL diagnostics in `MountPlanningError` constructions in `projection.py`: none.

## User-Authorized Final URL-Identity Follow-up

- Authorization: the user explicitly authorized this final diagnostic-only correction in the dedicated worktree.
- Preserved every prior correction entry above; this section appends current-final evidence without rewriting history.
- Hardened `_repo_name` to prefer a repository path basename, use a safe hostname for authority-only URLs, preserve SSH/scp-like basenames, strip query/fragment, and use a neutral `repository` identity when URL parsing fails.
- Audited all 13 `_repo_name` call sites in `projection.py`: six construct planning paths and seven render `MountPlanningError` diagnostics. All now share the credential-safe identity behavior; no raw URL diagnostic remains.
- Scope remained diagnostic identity and focused tests only. Architecture, planning behavior, provider/CLI contracts, specs/design/tasks, and protected changes are unchanged.

### TDD Cycle Evidence

| Test File | Layer | RED | GREEN |
|---|---|---|---|
| `tests/manifest/test_projection.py` | Unit | `uv run pytest tests/manifest/test_projection.py -q` — exit 1, 1 failed and 42 passed; authority-only `https://username:password@example.com` returned `username:password@example.com` | `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 44 passed in 0.44s |

### Runtime Probe

- Explicit nine-case `_repo_name` probe covered path-bearing HTTPS userinfo, authority-only HTTPS userinfo, query, fragment, SSH URL, scp-like URL, normal HTTPS, unrestricted fallback, and malformed URL fallback.
- Exact outputs: `repo`, `example.com`, `repo`, `repo`, `repo`, `repo`, `repo`, `unrestricted-repo`, `repository`.
- The probe asserted that none of the supplied usernames, passwords, tokens, query values, or fragment values appeared in any output; exit 0.

### Current Full Quality Gate

- `uv run pytest` — exit 0, 599 passed, 6 deselected in 4.12s.
- `uv run lint-imports` — exit 0, 6 contracts kept, 0 broken.
- `uv run ruff check .` — exit 0, all checks passed.
- `uv run ruff format --check .` — exit 0, 113 files already formatted.
- `uv run mypy` — exit 0, no issues found in 110 source files.
- `git diff --check` — exit 0, no output.

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/manifest/test_projection.py -q` — exit 0, 44 passed in 0.44s. |
| Runtime harness command/scenario and exact result | Explicit nine-case `_repo_name` probe — exit 0; every output matched its safe identity and contained none of the supplied secrets. |
| Rollback boundary | Revert only the `_repo_name` hardening in `src/odoo_forge/manifest/projection.py`, its table-driven regression in `tests/manifest/test_projection.py`, and this appended section. |

## Later Structural-Lock Correction (Historical Evidence)

- This correction occurred after the URL-identity follow-up above. It records the later review/remediation history and does not replace the current-final independent gate below.
- Review lineage: `review-d8c9511053c07302`; frozen findings: R3-001 and R4-001.
- Defect: matching the lock's manifest hash proved manifest identity only; it did not prove that the lock contained every required layer and repository or that each locked repository identity was complete and canonical.
- Pure correction: `_validate_lock_structure` now validates canonical core, Git, `PublishedLayer`, and `Override` identities and rejects structurally incomplete locks before mount planning proceeds.

### TDD and Review Evidence

| Test File | Layer | RED | GREEN |
|---|---|---|---|
| `tests/manifest/test_projection.py` | Unit | The current-hash truncated-lock regression did not raise, proving that hash agreement alone bypassed repository/layer completeness validation | 76 focused tests passed after the pure structural validation correction |

- Focused GREEN also passed Ruff check, Ruff format check, mypy, and `git diff --check`.
- Correction size: 63 authored changed lines; native accounting reported 62 lines against an 80-line forecast.
- Terminal review approved the correction receipt. Remaining INFO findings are explicitly non-blocking.

## Current Final State (Independent Verification)

These results are the latest independent full-gate evidence. Earlier gate counts and correction-specific results above remain historical snapshots.

- `uv run pytest` — exit 0, 599 passed, 6 deselected.
- `uv run lint-imports` — exit 0, 6 contracts kept, 0 broken.
- `uv run ruff check .` — exit 0, all checks passed.
- `uv run ruff format --check .` — exit 0, all files already formatted.
- `uv run mypy` — exit 0, no issues found.
- `git diff --check` — exit 0, no output.
- Focused requirement gate — exit 0, 115 passed, 6 deselected.
