# Tasks: Phase 2 Slice 3 — Workspace Projection

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR-1 ~300-380, PR-2a ~280-340, PR-2b ~250-300, PR-3 ~250-350, PR-4 ~160-250 |
| 400-line budget risk | Low-Medium (every PR now under budget) |
| Chained PRs recommended | Yes (5) |
| Suggested split | PR 1 → PR 2a → PR 2b → PR 3 → PR 4 |
| Delivery strategy | ask-on-risk (resolved: split, no exception) |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low-Medium

### Suggested Work Units

Coordinator-confirmed delivery decision: the original PR-2 (adapter + purity contract) was split into two PRs so every PR in the chain stays within the 400-line review budget with no `size:exception` needed. Final chain is 5 PRs.

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `category` field, `WorkspaceError` family, `classify_root`/`plan_projection`, `workspace_provider.py` port | PR 1 | base = feature/tracker branch; zero I/O, fakeable |
| 2a | Pure `project_workspace` execution loop + `odoo_forge_workspace` checkout adapter + 4th import-linter contract | PR 2a | base = PR 1 branch; introduces the sibling package and purity contract |
| 2b | Pure `materialize_state` mapping + `odoo_forge_workspace` scan adapter + promote/worktree adapter | PR 2b | base = PR 2a branch; completes the adapter's 3 port methods |
| 3 | `forge project` CLI + `forge validate` scan wiring | PR 3 | base = PR 2b branch; consumes PR 1/2a/2b use-cases |
| 4 | `forge unlock` CLI | PR 4 | base = PR 3 branch; independent feature, smallest unit |

Recommended review lenses: review-resilience + review-reliability (filesystem/subprocess boundary, partial-failure/idempotency modes) for PR-2a, PR-2b, PR-3.

## PR-1: Pure Core — Schema, Errors, Mapping, Port

### Phase 1: Foundation
- [x] 1.1 Add optional `category: Literal["custom","community","localization","enterprise"] | None = None` to `GitLayer`/`PublishedLayer` in `manifest/schema.py`
- [x] 1.2 RED: `test_errors.py::test_workspace_error_family` — `ProjectionError`/`CheckoutError`/`ScanError`/`PromotionError`/`AlreadyUnlockedError` subclass new `WorkspaceError(ManifestError)`
- [x] 1.3 GREEN: add `WorkspaceError` family to `manifest/errors.py`

### Phase 2: classify_root + plan_projection (new `manifest/projection.py`)
- [x] 2.1 RED: `test_projection.py::test_classify_root_*` — default custom, explicit category, enterprise overrides category, core→community, never returns "worktrees"
- [x] 2.2 GREEN: implement `MOUNT_ROOTS` table + `classify_root(layer) -> MountRoot`
- [x] 2.3 RED: `test_projection.py::test_plan_projection_preserves_lock_order`
- [x] 2.4 GREEN: implement `plan_projection(manifest, lock) -> WorkspacePlan` (`WorkspacePlanEntry` per repo)
- [x] 2.5 RED: `test_projection.py::test_plan_projection_orphaned_layer_raises`
- [x] 2.6 GREEN: raise `ProjectionError` naming orphaned layer, no partial plan returned

### Phase 3: Port
- [x] 3.1 Create `ports/workspace_provider.py` — `@runtime_checkable WorkspaceProvider` Protocol (`checkout`, `scan`, `promote`)

**PR-1 Gate**: `uv run pytest` + `uv run lint-imports` (3 contracts, no regression).

## PR-2a: Pure project_workspace + Checkout Adapter + 4th Contract — STATUS: DONE (this apply batch)

### Phase 4: Pure execution use-case (`manifest/projection.py`)
- [x] 4.1 RED: `test_projection.py::TestProjectWorkspace::test_calls_provider_checkout_per_entry` (fake in-memory provider, no I/O)
- [x] 4.2 GREEN: implement `project_workspace(plan, provider) -> None` (deviation from `-> WorkspaceReport` — see Known Deviation note below)

### Phase 5: Checkout adapter `src/odoo_forge_workspace/`
- [x] 5.1 Create `odoo_forge_workspace/__init__.py` + `provider.py` (`GitWorkspaceProvider` scaffold)
- [x] 5.2 RED: `tests/adapters/test_workspace_provider.py` — idempotent skip, dirty refusal, linked-worktree refusal, clean-replace, missing-git-binary (monkeypatch `subprocess.run`)
- [x] 5.3 GREEN: implement `checkout` — temp clone + `os.replace`, skip if `HEAD` matches, refuse dirty/worktree with `CheckoutError`

### Phase 6: Purity contract
- [x] 6.1 Add `odoo_forge_workspace` to `pyproject.toml` root packages + wheel include
- [x] 6.2 Add 4th `[[tool.importlinter.contracts]]`: forbidden, `source_modules=["odoo_forge"]`, `forbidden_modules=["odoo_forge_workspace"]`
- [x] 6.3 Verify `uv run lint-imports` — 4 kept, 0 broken

**PR-2a Gate**: `uv run pytest` (114 passed) + `uv run lint-imports` (4 kept, 0 broken) — PASSED.

**Known Deviation (PR-2a)**: `project_workspace(plan, provider)` returns `None`, not `WorkspaceReport` as
written in tasks.md/design.md. Neither the spec nor the design define `WorkspaceReport`'s fields anywhere —
it appears only as a bare return-type name. The spec's actual behavioral requirements for `forge project`
(atomic per-step checkout, stop-on-failure, no partial-step rollback) are fully satisfiable via plain
iteration with exceptions propagating uncaught, mirroring `build_lock(manifest, provider) -> Lockfile`'s
precedent exactly (a pure loop over provider calls, no wrapper report object). Flag for sdd-verify /
judgment-day: confirm PR-3's `forge project` CLI does not need a `WorkspaceReport` for its exit-code/message
contract before this is locked in permanently.

## PR-2b: Pure materialize_state + Scan/Promote Adapters — STATUS: DONE (this apply batch)

### Phase 7: Pure scan mapping (`manifest/projection.py`)
- [x] 7.1 RED: `test_projection.py::TestMaterializeState::test_layout_and_worktrees_precedence` (+ missing-directory, malformed-path, outside-any-root cases)
- [x] 7.2 GREEN: implement `materialize_state(scanned, roots) -> MaterializedState`

### Phase 8: Scan adapter (`odoo_forge_workspace/provider.py`)
- [x] 8.1 RED: `test_workspace_provider.py::TestScan::test_scan_reads_head_and_remote_url_skips_non_git_dirs` (+ nonexistent-root, corrupted-HEAD, credential-leak cases)
- [x] 8.2 GREEN: implement `scan` — `git -C rev-parse HEAD` / `remote get-url origin`, skip non-`.git` dirs, raise `ScanError` on corrupted HEAD

### Phase 9: Promote/worktree adapter (`odoo_forge_workspace/provider.py`)
- [x] 9.1 RED: `test_workspace_provider.py::TestPromote::test_promote_creates_worktree_and_raises_if_already_writable` (+ promote-failure case)
- [x] 9.2 GREEN: implement `promote` — `git worktree add -b <branch> -- <dest>` from `source`, raise `AlreadyUnlockedError` if `dest` exists, `PromotionError` on failure

**PR-2b Gate**: `uv run pytest` (129 passed) + `uv run lint-imports` (4 kept, 0 broken, no regression) — PASSED.

## PR-3: `forge project` CLI + `forge validate` Scan Wiring

### Phase 10: forge project
- [ ] 10.1 RED: `tests/cli/test_project.py::test_valid_lock_projects_every_layer` (CliRunner, monkeypatched `_make_workspace_provider`)
- [ ] 10.2 GREEN: add `_make_workspace_provider()` + `forge project [--manifest][--lock]` in `main.py` calling `plan_projection` + `project_workspace`
- [ ] 10.3 RED: `test_project.py::test_mid_plan_checkout_failure_stops_cleanly_exits_nonzero`
- [ ] 10.4 GREEN: catch `WorkspaceError` family, exit 1 with single-cause message, no traceback, no touch of completed steps

### Phase 11: forge validate scan wiring
- [ ] 11.1 RED: `tests/cli/test_validate.py::test_drift_detected_against_real_scanned_workspace`
- [ ] 11.2 GREEN: `forge validate` calls `provider.scan(MOUNT_ROOTS)` + `materialize_state`, passes real `MaterializedState` into `detect_drift` (replaces hardcoded `None`)

**PR-3 Gate**: `uv run pytest` + `uv run lint-imports` + manual `forge --help`.

## PR-4: `forge unlock` CLI

### Phase 12: forge unlock
- [ ] 12.1 RED: `tests/cli/test_unlock.py::test_unlock_succeeds_and_prints_branch`
- [ ] 12.2 GREEN: `forge unlock --layer NAME --repo URL` in `main.py` calling `provider.promote` via `unlock`
- [ ] 12.3 RED: `test_unlock.py::test_already_unlocked_exits_nonzero_single_cause`
- [ ] 12.4 GREEN: catch `AlreadyUnlockedError`/`ScanError`, exit 1 with clean message

**PR-4 Gate**: full `uv run pytest` + `uv run lint-imports` (4 kept/0 broken) + manual smoke `forge project` → `forge validate` → `forge unlock`.

## Scope Guardrails
- No override (fork url/ref substitution) application — re-deferred, do not implement.
- `unlock` is repo-level only, never bulk-promotes a layer.
- Mount roots are the fixed 5-entry table only — no generic `/mnt/{name}` mapping.
