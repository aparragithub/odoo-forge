# Apply Progress: Phase 2 Slice 3 — Workspace Projection

## Batch 1 (this session) — PR-1: Pure Core

**Mode**: Strict TDD (RED → GREEN, no REFACTOR needed)
**Branch**: `sdd/phase-2-slice-3-pr1-core`
**Scope**: PR-1 only (per orchestrator instruction). PR-2a/2b/3/4 NOT started.

### Completed Tasks (PR-1)
- [x] 1.1 Add optional `category` field to `GitLayer`/`PublishedLayer`
- [x] 1.2 RED: `test_errors.py::test_workspace_error_family`
- [x] 1.3 GREEN: `WorkspaceError` family in `manifest/errors.py`
- [x] 2.1 RED: `test_projection.py::TestClassifyRoot::*`
- [x] 2.2 GREEN: `MOUNT_ROOTS` + `classify_root(layer) -> MountRoot`
- [x] 2.3 RED: `test_projection.py::test_plan_mirrors_lock_order`
- [x] 2.4 GREEN: `plan_projection(manifest, lock) -> WorkspacePlan`
- [x] 2.5 RED: `test_projection.py::test_orphaned_lock_layer_raises_and_returns_no_partial_plan`
- [x] 2.6 GREEN: `ProjectionError` naming orphaned layer
- [x] 3.1 `ports/workspace_provider.py` — `@runtime_checkable WorkspaceProvider` Protocol

### Files Changed
| File | Action | What Was Done |
|------|--------|----------------|
| `src/odoo_forge/manifest/schema.py` | Modified | Added `LayerCategory` type alias + optional `category: LayerCategory \| None = None` on `GitLayer`/`PublishedLayer`. Back-compat: absent on all legacy fixtures/locks. |
| `src/odoo_forge/manifest/errors.py` | Modified | Added `WorkspaceError(ManifestError)` base + `ProjectionError`, `CheckoutError`, `ScanError`, `PromotionError`, `AlreadyUnlockedError` (all direct `WorkspaceError` subclasses). |
| `src/odoo_forge/manifest/projection.py` | Created | Pure `classify_root(layer) -> MountRoot`, pure `plan_projection(manifest, lock) -> WorkspacePlan`, `MOUNT_ROOTS` fixed 5-root table, `WorkspacePlanEntry`/`WorkspacePlan`/`ScannedRepo` models, local `_repo_name` helper. Zero I/O. |
| `src/odoo_forge/ports/workspace_provider.py` | Created | `@runtime_checkable WorkspaceProvider` Protocol: `checkout(url, commit, dest) -> None`, `scan(roots) -> list[ScannedRepo]`, `promote(source, dest, branch) -> None`. No adapter — interface only. |
| `tests/manifest/test_schema.py` | Modified | Added 3 tests for `category` field default/explicit value on `GitLayer`/`PublishedLayer`. |
| `tests/manifest/test_errors.py` | Modified | Added `test_workspace_error_family`. |
| `tests/manifest/test_projection.py` | Created | `TestClassifyRoot` (6 scenarios incl. parametrized "never worktrees" check) + `TestPlanProjection` (order preservation, orphan-raises). |
| `tests/ports/test_workspace_provider.py` | Created | Protocol conformance test (fake provider) + non-conformance test. |
| `openspec/changes/phase-2-slice-3-workspace-projection/tasks.md` | Modified | Marked PR-1 tasks `[x]`. |

### TDD Cycle Evidence

| Task | RED (test written first) | GREEN (implementation passes) | REFACTOR |
|------|---------------------------|-------------------------------|----------|
| 1.1 category field | `test_schema.py::test_git_layer_category_defaults_to_none` (+2 more) — failed with `AttributeError: 'PublishedLayer' object has no attribute 'category'` | Added `LayerCategory` + field; 11/11 schema tests pass | None needed |
| 1.2/1.3 WorkspaceError family | `test_errors.py::test_workspace_error_family` — failed with `ImportError: cannot import name 'AlreadyUnlockedError'` | Added error family; 2/2 error tests pass | None needed |
| 2.1/2.2 classify_root | `test_projection.py::TestClassifyRoot::*` — failed with `ModuleNotFoundError: No module named 'odoo_forge.manifest.projection'` | Implemented `classify_root`; 14/14 projection tests pass | None needed |
| 2.3/2.4 plan_projection order | `test_plan_mirrors_lock_order` — same ModuleNotFoundError (collected together) | Implemented `plan_projection`; passes | None needed |
| 2.5/2.6 orphan raises | `test_orphaned_lock_layer_raises_and_returns_no_partial_plan` — same ModuleNotFoundError | `ProjectionError` raised naming layer, no partial `WorkspacePlan` constructed | None needed |
| 3.1 WorkspaceProvider port | `test_workspace_provider.py::test_conforming_class_satisfies_workspace_provider_protocol` — failed with `ModuleNotFoundError: No module named 'odoo_forge.ports.workspace_provider'` | Implemented Protocol; 3/3 port tests pass | None needed |

### Test/Lint Evidence (actual command output)

```
$ uv run pytest -q
........................................................................ [ 69%]
................................                                         [100%]
104 passed in 0.38s
```
(baseline before this batch: 83 passed — net +21 new tests, 0 regressions)

```
$ uv run lint-imports
Contracts
---------
Analyzed 29 files, 51 dependencies.
-----------------------------------
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Contracts: 3 kept, 0 broken.
```

### Deviations from Design

**Flagged for PR-2a/2b review**: `WorkspaceProvider.scan`/`.promote` signatures were
implemented per the **design doc's** `Interfaces` section
(`scan(roots) -> list[ScannedRepo]`, `promote(source, dest, branch) -> None`), not the
**spec's** literal text (`scan(mount_roots) -> MaterializedState`,
`promote(target_path) -> str`). Rationale: design architecture decision #4 requires the
adapter to return raw `ScannedRepo` values so a separate pure `materialize_state`
(PR-2b, task 7) can do the layer-attribution mapping — this is the hexagonal-purity
argument (dumb adapter, pure core mapping) and is what task 7-9 in tasks.md actually
build toward. The CLI-observable contract from spec (`forge unlock` reports the new
branch name) is preserved because the future `unlock` use-case will compute the branch
name itself and pass it into `promote`, rather than reading it back from a return value.
No code in PR-1 depends on this resolution being final — it only affects the Protocol's
type signature, which is not otherwise exercised in this batch. Recommend sdd-verify /
judgment-day confirm this reconciliation before PR-2a implements the checkout adapter
against it.

### Issues Found
None.

### Remaining Tasks
- [ ] PR-2a: Phase 4 (`project_workspace`), Phase 5 (checkout adapter), Phase 6 (4th import-linter contract)
- [ ] PR-2b: Phase 7 (`materialize_state`), Phase 8 (scan adapter), Phase 9 (promote/worktree adapter)
- [ ] PR-3: Phase 10 (`forge project` CLI), Phase 11 (`forge validate` scan wiring)
- [ ] PR-4: Phase 12 (`forge unlock` CLI)

### Workload / PR Boundary
- Mode: chained PR slice (feature-branch-chain, 5 PRs total)
- Current work unit: PR-1 (base = feature/tracker branch `sdd/phase-2-slice-3-pr1-core`)
- Boundary: starts from zero (no prior workspace-projection code existed); ends with
  the full pure-core planning layer (schema field, error family, `classify_root`,
  `plan_projection`, `WorkspaceProvider` port) complete and tested, with zero I/O and
  zero adapter code — ready for PR-2a to build the execution loop + checkout adapter on
  top.
- Estimated review budget impact: new/modified diff is well under 400 lines (2 new
  source files ~150 lines combined, 2 modified source files ~50 lines added, 4 test
  files ~230 lines) — within the "PR-1 ~300-380" forecast, low review risk.

### Status
12/12 PR-1 tasks complete (12/48 tasks in the full 5-PR chain). Ready for sdd-verify
on PR-1, then sdd-apply again for PR-2a.
