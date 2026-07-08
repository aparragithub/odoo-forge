# Proposal: Phase 2 Slice 3 — Workspace Projection

## Intent
Slices 1–2b deliver a pure manifest, drift detection, and a pinned `project.lock` — but nothing yet puts layers on disk. This slice is the FIRST projection: it checks out the locked layers onto the developer filesystem under the fixed mount roots the container already scans, scans that tree back into a real `MaterializedState`, and lets a developer PROMOTE a read-only layer to a writable working copy (`unlock`). It also activates a currently-dead path: `forge validate` calls `detect_drift(..., materialized=None)` today (main.py:144) — after this slice a real scan feeds it end-to-end. High-risk seam (git checkout + filesystem writes), so it mirrors the Slice 2b hexagonal split: pure core, new port, new adapter package, new purity contract.

## Scope
### In Scope
- Pure `plan_projection(lock) -> WorkspacePlan` use-case in `odoo_forge` (Protocol-injected, no I/O).
- Fixed 5-root `Layer/role → /mnt/*` lookup (`worktrees|custom|community|localization|enterprise`) honoring the shipped `factory/entrypoint.sh` `build_addons_path()` scan.
- New `WorkspaceProvider` port (`ports/workspace_provider.py`): checkout-at-commit, scan, promote.
- New sibling adapter package (e.g. `odoo_forge_workspace`) doing real git checkout/worktree + `/mnt/*` writes.
- Workspace scan → real `MaterializedState`; `forge validate` wired to pass it.
- `unlock` = PROMOTE a read-only layer to writable branch/worktree (design §2.2), NOT teardown.
- New CLI commands (project/projection + `unlock`), composition-root wiring, resilient boundary.
- 4th import-linter contract forbidding `odoo_forge -> odoo_forge_workspace`.

### Out of Scope / Non-goals
- Override application (fork url/ref substitution) — RE-DEFERRED; explicit non-goal.
- Docker/local-backend mount execution (bind mounts, OS differences) — Slice 4.
- Retry/backoff/observability on checkout — deferred (note in design).
- Generic `/mnt/{name}` mapping — rejected (breaks shipped entrypoint scan).

## Capabilities
### New Capabilities
- `workspace-projection`: `plan_projection`, mount-root mapping, `WorkspaceProvider` port + adapter, scan → `MaterializedState`.
- `forge-workspace-cli`: projection + `unlock` commands wired at composition root.
### Modified Capabilities
- `manifest`: `forge validate` now receives real materialized state (activates `detect_drift` materialized path).

## Approach
Mirror Slice 2b I/O boundary: pure core use-case with a `Protocol` param, concrete filesystem/git behavior in a new sibling package, CLI as composition root, additive import-linter contract. Fixed-root lookup keyed by layer role (core/enterprise/localization/client), not free-text `Layer.name`.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/manifest/` | New | `plan_projection` use-case + mount-root mapping |
| `src/odoo_forge/manifest/schema.py` | Modified? | possible additive `role`/`category` to classify layers into 5 roots |
| `src/odoo_forge/manifest/state.py` | Consumed | scan populates `MaterializedState` |
| `src/odoo_forge/ports/workspace_provider.py` | New | `WorkspaceProvider` Protocol |
| new `src/odoo_forge_workspace/` | New | checkout/worktree + `/mnt/*` writes |
| `src/odoo_forge_cli/main.py` | Modified | projection + `unlock` commands, wiring |
| `pyproject.toml` | Modified | 4th import-linter contract |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Layer→root classification (`Layer.name` is free text) | High | additive `role` field / documented convention; keep back-compat |
| 4th contract breaks core purity | Med | add not weaken; fake provider in core tests |
| `unlock` misread as teardown | Med | LOCKED as promote-to-writable (§2.2); spec scenarios pin it |
| Partial checkout leaves dirty `/mnt/*` | Med | resilient boundary; scan reports actual state |
| Slice spans projection+scan+unlock → over 400 lines | High | tasks-phase MUST forecast; likely chained PRs |

## Review-Budget Note
Large slice (projection + scan + unlock + new package). Delivery strategy `ask-on-risk`. `sdd-tasks` MUST forecast against the 400-line/PR budget and likely recommend chained PRs (candidate split: adapter+port+mapping / scan+validate wiring / unlock). Recommended lenses: review-resilience + review-reliability (filesystem/git boundary, partial-failure and drift correctness).

## Open Questions (for sdd-spec / sdd-design)
1. How is a `Layer` classified into one of the 5 fixed roots — additive `role` field vs documented naming convention?
2. `unlock` mechanism: `git worktree` under `/mnt/worktrees` vs branch-in-place; input granularity (layer vs repo).
3. Scan definition: what makes a `/mnt/*` checkout a `MaterializedRepo` (`.git` HEAD SHA per repo dir?).
4. Does projection stop at checkout, or also emit the plan for Slice 4 to mount?
5. Placement of `plan_projection` (core use-case with Protocol param, mirroring `build_lock`).

## Rollback Plan
Additive slice: new package + new commands + additive core use-case/port + optional additive schema field. Revert the branch(es). No existing workspace consumers; `project.lock` format unchanged, no data migration.

## Dependencies
- Slices 2a/2b merged (`build_lock`, canonical `Lockfile`) — DONE.
- System `git` binary at runtime; `factory/` mount-root convention (already shipped).

## Success Criteria
- [ ] A projection command checks out each locked layer under the correct fixed `/mnt/*` root.
- [ ] A scan produces a real `MaterializedState`; `forge validate` runs `detect_drift` with it (no more `materialized=None`).
- [ ] `unlock` promotes a chosen read-only layer to a writable working branch/worktree (not teardown).
- [ ] import-linter 4 kept / 0 broken; `odoo_forge` imports zero filesystem/git; adapter not importable from core.
- [ ] Mount-root mapping conforms to `factory/entrypoint.sh` scan (5 fixed roots).
