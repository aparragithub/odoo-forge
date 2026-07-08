# Apply Progress: Phase 2 Slice 3 — Workspace Projection

Progress: Slice 3 PR-1 DONE (merged, PR #9); PR-2a DONE; PR-2b DONE; PR-3 DONE (merged, PR #8); PR-4 DONE (this batch, branch sdd/phase-2-slice-3-pr4-unlock-cli, base = PR-3 merged main). FULL 5-PR CHAIN COMPLETE.

## PR-1/2a/2b/3 — DONE (unchanged from prior record, see apply-progress.md for full detail)
PR-1: category field + WorkspaceError family + classify_root/plan_projection + WorkspaceProvider port. pytest 104 passed, lint-imports 3 kept/0 broken.
PR-2a: pure project_workspace(plan, provider) -> None (deviation from -> WorkspaceReport, mirrors build_lock) + GitWorkspaceProvider.checkout (idempotent, dirty/worktree refusal, temp-clone+os.replace) + 4th import-linter contract. pytest 114 passed, lint-imports 4 kept/0 broken.
PR-2b: pure materialize_state(scanned, roots) + GitWorkspaceProvider.scan/promote adapters. pytest 129 passed, lint-imports 4 kept/0 broken.
PR-3: forge project CLI (_make_workspace_provider composition-root helper, plan_projection -> project_workspace inside one ManifestError resilient boundary) + forge validate wired to real scan -> materialize_state -> detect_drift (replaces dead materialized=None) + round-trip integration test + verify-follow-up credential-leak characterization test. pytest 137 passed, lint-imports 4 kept/0 broken.

## PR-4 — DONE

### Completed Tasks
- [x] 12.1-12.4 `forge unlock --manifest --layer NAME --repo URL` CLI command

### Files Changed (PR-4)
| File | Action | What Was Done |
|------|--------|----------------|\n| src/odoo_forge/manifest/projection.py | Modified | Added `UnlockPlan(source, dest, branch)` model + pure `plan_unlock(manifest, layer_name, repo_url) -> UnlockPlan`. Looks up the layer in the manifest (mirrors `plan_projection`'s name-join), classifies its mount root via the existing `classify_root`, derives `source = MOUNT_ROOTS[mount_root]/layer_name/repo_name`, `dest = MOUNT_ROOTS["worktrees"]/layer_name/repo_name`, `branch = f"unlock/{layer_name}/{repo_name}"`. Raises `ProjectionError` naming the layer when it has no matching manifest entry. Zero I/O — does NOT check `dest.exists()` itself (see decision below). |
| src/odoo_forge_cli/main.py | Modified | Added `forge unlock` command: reads+validates manifest, calls `plan_unlock` then `provider.promote(plan.source, plan.dest, plan.branch)` inside one `try/except ManifestError` resilient boundary (mirrors `project`/`lock`), exits 1 + single `error:` line + no traceback on `ProjectionError`/`AlreadyUnlockedError`/`PromotionError`/`ScanError` (all `WorkspaceError`/`ManifestError` subclasses), prints `unlocked '<layer>' at '<dest>' on branch '<branch>'` on success. |
| tests/cli/test_unlock.py | Created | `_FakeWorkspaceProvider` (records `promote` calls, raises `AlreadyUnlockedError` on demand) + 4 tests: succeeds and reports branch (custom layer); core layer resolves to `/mnt/community/core/odoo` source; already-unlocked exits 1 single-cause no-traceback; unknown layer exits 1 single-cause, no `promote` call made. |
| tests/manifest/test_projection.py | Modified | Added `TestPlanUnlock` with 3 pure unit tests: custom-layer source/dest/branch computation; core-layer source path (community root); unknown-layer raises `ProjectionError`. |
| openspec/changes/.../tasks.md | Modified | Marked PR-4 tasks [x] + gate evidence + `AlreadyUnlockedError` placement decision. |

### PR-4 Evidence
`uv run pytest -q` -> 144 passed (up from 137 baseline)
`uv run lint-imports` -> 4 kept, 0 broken
`uv run forge --help` -> shows validate/lock/project/unlock commands

### Decision: `AlreadyUnlockedError` placement (deferred from PR-2b/verify)
Kept in the adapter (`GitWorkspaceProvider.promote`'s `dest.exists()` guard, shipped in PR-2b) rather than moved into a pure core planning helper. Rationale: existence-of-a-worktree-on-disk is a live filesystem fact subject to TOCTOU between when a pure plan is computed and when `promote` actually runs — checking it right before `git worktree add` in the adapter is race-safe, whereas a core-side check could go stale. `plan_unlock` stays pure/zero-I/O and only computes `source`/`dest`/`branch`, matching the design's split (core decides paths/branch; adapter executes the side effect and guards it).

### Deviations
None beyond the already-flagged-and-accepted PR-2a `project_workspace -> None` deviation (unaffected by PR-4). `plan_unlock`'s branch-naming convention (`unlock/<layer>/<repo>`) was not specified verbatim by spec/design (which left branch naming open) — chosen for determinism/readability, consistent with `plan_projection`'s deterministic target-path convention.

Status: 48/48 numbered tasks complete across the full 5-PR chain (PR-1 12/12, PR-2a 8/8, PR-2b 6/6, PR-3 6/6, PR-4 4/4) + 2 additional verify-requested/PR-4 characterization/unit tests beyond the numbered list. 144/144 tests passing, 4/4 import-linter contracts kept. Chain COMPLETE — ready for sdd-verify.

Related: tasks (#2326), spec (#2324), design (#2325), scope-decisions (#2322).
Test runner: `uv run pytest`. Import gate: `uv run lint-imports`.
