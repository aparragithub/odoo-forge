# Verification Report — Phase 2 Slice 3 (PR-1: Pure Core)

**Change**: phase-2-slice-3-workspace-projection
**Scope verified**: PR-1 ONLY (pure core: schema, errors, mapping, port)
**Branch**: sdd/phase-2-slice-3-pr1-core
**Mode**: Strict TDD (authoritative per orchestrator)
**Verdict**: PASS

## Completeness (PR-1 tasks)

| Task group | State |
|---|---|
| 1.1 `category` field (schema.py) | done, verified |
| 1.2/1.3 `WorkspaceError` family (errors.py) | done, verified |
| 2.1-2.6 `classify_root` + `plan_projection` (projection.py) | done, verified |
| 3.1 `WorkspaceProvider` port (ports/workspace_provider.py) | done, verified |

12/12 PR-1 tasks checked. No unchecked PR-1 implementation task.

## Runtime evidence

```
$ uv run pytest -q
104 passed in 0.44s
```

```
$ uv run lint-imports
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Contracts: 3 kept, 0 broken.
```

## PR-1 contract checks

1. **`category` field** — PASS. `LayerCategory = Literal["custom","community","localization","enterprise"]`; optional `category: LayerCategory | None = None` added to both `GitLayer` and `PublishedLayer`. Field default is `None`; `classify_root` maps `None`→`"custom"` (matches the reconciled spec's `| None = None` declaration). Back-compat proven by `test_git_layer_category_defaults_to_none` / `test_published_layer_category_defaults_to_none`. `lockfile.py` UNCHANGED (git status empty) — no lock-format change.

2. **`WorkspaceError` family** — PASS. `WorkspaceError(ManifestError)` base + `ProjectionError`, `CheckoutError`, `ScanError`, `PromotionError`, `AlreadyUnlockedError` (all direct subclasses). Covers the reconciled spec taxonomy. `test_workspace_error_family` asserts every subclass relationship.

3. **`classify_root` + `plan_projection`** — PASS. Both pure/provider-free/zero-I/O. `classify_root`: `CoreLayer`→`community`; `requires_edition=="enterprise"` wins over `category`; else explicit `category`; else `custom`; `"worktrees"` never returned (parametrized `test_never_returns_worktrees` across 7 layer shapes). `plan_projection` joins lock↔manifest by `.name` (incl. `"core"`), preserves `lock.layers` order (`test_plan_mirrors_lock_order` asserts layer/root/commit order), raises `ProjectionError` naming orphaned layer with no partial plan (raise occurs before any return).

4. **`WorkspaceProvider` port** — PASS. Interface-only `@runtime_checkable Protocol` with `checkout(url:str,commit:str,dest:Path)->None`, `scan(roots:Sequence[Path])->list[ScannedRepo]`, `promote(source:Path,dest:Path,branch:str)->None` — signatures MATCH the reconciled spec exactly. No implementation in core. Protocol conformance proven positive and negative (`test_conforming_class_satisfies_workspace_provider_protocol`, `test_non_conforming_class_does_not_satisfy_protocol`).

5. **Purity** — PASS. `lint-imports` = 3 kept / 0 broken. Core stays pure; no `odoo_forge_workspace` import (package not created yet). 4th contract correctly deferred to PR-2a.

6. **Tests** — PASS. 104 passed (baseline 83, net +21). Tests are meaningful and test-first-shaped: parametrized edge coverage, order+root+commit assertions, orphan-raise with `match=`, positive/negative Protocol checks — not tautological.

7. **Scope discipline** — PASS. No adapter package (`src/odoo_forge_workspace` absent), no 4th contract (3 in pyproject.toml), no CLI changes (`main.py` untouched). No PR-2a/2b/3/4 work leaked.

## Reconciled deviation (now resolved)

The apply/tasks docs flagged that `scan`/`promote` signatures followed the DESIGN (`scan(roots)->list[ScannedRepo]`, `promote(source,dest,branch)->None`) instead of the spec's earlier literal text. The RECONCILED spec now declares exactly these signatures, so the implementation and spec are consistent. No action needed.

## Residual (non-blocking) debt

- `ScannedRepo`, `MOUNT_ROOTS`, `WorkspacePlanEntry` are introduced in PR-1 though `ScannedRepo`/`materialize_state` are consumed later. Justified: `ScannedRepo` is required by the port signature; not scope creep.
- Spec requirements `materialize_state`, `project_workspace`/execution loop, `unlock`, and the CLI capabilities remain UNIMPLEMENTED by design — correctly deferred to PR-2a/2b/3/4 per the chain plan. These are out of PR-1 scope, not gaps.

## Verdict

PASS. PR-1 fully satisfies its contract with green runtime evidence. Ready to proceed to PR-2a.

---

# Verification Report — Phase 2 Slice 3 (PR-2a: project_workspace + Checkout Adapter + 4th Contract)

**Scope verified**: PR-2a ONLY (pure `project_workspace` loop, `GitWorkspaceProvider.checkout`, 4th import-linter contract + packaging)
**Branch**: sdd/phase-2-slice-3-pr2a-checkout-adapter
**Mode**: Strict TDD (authoritative per orchestrator)
**Verdict**: PASS WITH WARNINGS
**Counts**: CRITICAL 0 · WARNING 2 · SUGGESTION 4

## Runtime evidence

```
$ uv run pytest
114 passed in 0.40s
```

```
$ uv run lint-imports
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Contracts: 4 kept, 0 broken.
```

## PR-2a contract checks

1. **Pure `project_workspace(plan, provider)`** — PASS. Provider-injected via `WorkspaceProvider` Protocol under `TYPE_CHECKING` only (string annotation), zero runtime import of any adapter. Loops `plan.steps` in order calling `provider.checkout(url, commit, target_path)` per entry; exceptions propagate uncaught (stop-on-failure). Genuinely pure — import-linter confirms core clean. Fake-tested (`TestProjectWorkspace`): per-entry call order + empty-plan zero-call.

2. **`GitWorkspaceProvider.checkout`** — PASS. Atomicity: clone into `tempfile.mkdtemp(dir=dest.parent)` sibling, `git checkout --detach <commit>`, `rmtree(dest)` then `os.replace(clone, dest)`; `except BaseException: rmtree(tmp, ignore_errors=True); raise` leaves NO half-cloned dir at `dest` on failure. Subprocess safety: ALL calls via `_run(argv: list[str])`, argv-list only, NO `shell=True` anywhere — no shell-injection surface. Non-interactive env (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=""`, pinned `LANG`/`LC_ALL`). Idempotent: `HEAD == commit` → early no-op. Refuses to clobber: linked worktree (`.git` is a file) → `CheckoutError`; dirty checkout at wrong commit → `CheckoutError`, dest never destroyed. Error taxonomy: missing binary, timeout, non-zero rc all map to `CheckoutError`.

3. **4th import-linter contract** — PASS. `[[tool.importlinter.contracts]]` "Core never imports the workspace adapter": forbidden, `source_modules=["odoo_forge"]`, `forbidden_modules=["odoo_forge_workspace"]`. Package registered in `root_packages` AND wheel `packages`. `lint-imports` = 4 kept / 0 broken.

4. **Tests** — PASS. 114 passed (baseline 104, +10). 8 adapter tests behavior-first: happy clone+replace, idempotent skip, dirty refusal (no clone, dest preserved), linked-worktree refusal, clean-replace-at-wrong-commit (stale marker gone), missing-git-binary → CheckoutError, scan/promote NotImplementedError scope guard, Protocol isinstance. Not tautological.

5. **Scope discipline** — PASS. `scan`/`promote` stubbed to `NotImplementedError` (PR-2b) — correct. `materialize_state` NOT in core (only a docstring mention). No `forge project`/`forge unlock` CLI, no `_make_workspace_provider` (PR-3/4). No `factory/` dir exists/touched.

6. **`WorkspaceReport` deviation** — ACCEPTED (no code change recommended). `project_workspace` returns `None`. The spec's `forge project` contract (atomic per-step, stop-on-failure, exit non-zero naming failing repo, no partial-step rollback) is fully satisfied by an exception-propagating loop, mirroring `build_lock(...) -> Lockfile`'s side-effect-loop precedent. `WorkspaceReport` appears only as a bare unschematized return-type name in design/tasks. Does NOT constrain PR-3: the CLI wraps the call in `try/except WorkspaceError`; `CheckoutError` messages carry the failing clone argv (incl. url) and dest, so the failing repo is nameable without a report object. Recommend reconciling the DOCS (drop `WorkspaceReport` from design/tasks) rather than adding the type.

## Warnings

- **WARNING (process, not code)**: PR-2a changes are UNCOMMITTED. `git diff main...HEAD` is empty (HEAD == PR-1 merge). Working tree carries modified `projection.py`/`pyproject.toml`/`test_projection.py`/`tasks.md` + untracked `src/odoo_forge_workspace/` + `tests/adapters/test_workspace_provider.py`. apply-progress marks PR-2a DONE but no PR-2a commit exists. Orchestrator MUST commit before opening the PR.
- **WARNING (doc drift)**: design/tasks Interfaces still name `project_workspace(...) -> WorkspaceReport`; code returns `None`. Reconcile docs.

## Suggestions

- **SUGGESTION**: Option-injection hardening — add `--` end-of-options before positional `url`/`commit` in `git clone`/`git checkout`. Low risk (commits are 40-hex SHAs pinned by build_lock, argv-list already blocks shell injection); defense-in-depth only.
- **SUGGESTION**: No test explicitly guards against a `shell=True` regression. Add an assertion in the fake `subprocess.run` that `shell` is falsy.
- **SUGGESTION**: The `subprocess.TimeoutExpired -> CheckoutError` branch in `_run` is untested.
- **SUGGESTION**: Cosmetic — the `.marker` sanity assert in `test_checkout_clones_to_temp_and_replaces_into_dest` is trivially true (weak, harmless).

## Verdict

PASS WITH WARNINGS. PR-2a fully satisfies its contract with green evidence (114 passed, 4 kept/0 broken). Subprocess is argv-list/no-shell, checkout is atomic with clean failure cleanup and dirty/worktree refusal, error taxonomy correct. Zero CRITICAL. Ready to proceed to PR-2b once the working tree is committed. WorkspaceReport doc drift should be reconciled (docs, not code).

---

# Verification Report — Phase 2 Slice 3 (PR-2b: Pure materialize_state + Scan/Promote Adapters)

**Scope verified**: PR-2b ONLY (pure `materialize_state` + `_match_root_and_layer` in core; `GitWorkspaceProvider.scan`/`promote`; generalized `_run`)
**Branch**: sdd/phase-2-slice-3-pr2b-scan-promote (base = PR-2a branch)
**Mode**: Strict TDD (authoritative per orchestrator)
**Verdict**: PASS WITH WARNINGS
**Counts**: CRITICAL 0 · WARNING 2 · SUGGESTION 3

## Runtime evidence (exact)

```
$ uv run pytest -q
........................................................................ [ 55%]
.........................................................                [100%]
129 passed in 0.43s
```

```
$ uv run lint-imports
Analyzed 32 files, 62 dependencies.
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Contracts: 4 kept, 0 broken.
```

129 passed (baseline 114, net +15). 4 contracts kept / 0 broken — no purity regression.

## PR-2b contract checks

1. **Pure `materialize_state(scanned, roots)`** — PASS. Lives in `odoo_forge/manifest/projection.py` (core), zero I/O, zero adapter import (import-linter confirms). Derives layer name from the `/mnt/<root>/<layer>/...` path segment via `_match_root_and_layer` (`path.relative_to(base)`, `parts[0]` = layer), groups repos by layer keyed by `url`. Worktrees precedence is an order-independent two-pass (read-only entries first, then `worktrees`-root entries overwrite same-`url` keys). Output shape (`MaterializedLayer.name` = layer segment, `MaterializedRepo.url`/`.commit` verbatim from scan) EXACTLY satisfies `detect_drift` matching. Edge cases covered: empty scan → empty state; malformed path (missing `<layer>`) and path outside any root → `ScanError` naming the path.

2. **materialize_state <-> detect_drift round-trip** — PASS (traced), UNTESTED at integration level (see WARNING). Trace: `plan_projection` emits `target_path = MOUNT_ROOTS[root]/<lock_layer.name>/<repo_name>`; `scan` reports `path=target_path`, `url=remote.origin.url` (== `repo.url`), `commit=HEAD` (== locked commit); `materialize_state` recovers `layer_name = lock_layer.name` (matches `detect_drift`'s `materialized_by_name` lookup) and `MaterializedRepo(url=repo.url, commit=locked)` (matches `materialized_by_url` lookup + commit compare). Result: `is_clean = True` for a fully-projected tree; `not_materialized` for a missing directory (materialize_state omits it). Correct against `state.py`/`drift.py`. This finally makes the previously-dead `detect_drift(..., materialized=<real state>)` path usable — wiring into `forge validate` is PR-3 scope.

3. **`GitWorkspaceProvider.scan(roots)`** — PASS. Adapter stays DUMB: returns raw `ScannedRepo{path,url,commit}`, no layer/mount-root knowledge, no `MaterializedState`. Discovery bounded: `os.walk` per root; a dir containing `.git` is treated as one repo and `dirnames[:] = []` prunes descent (no nested-repo walk). Non-existent roots skipped; non-git dirs skipped silently. Reads `git -C <path> rev-parse HEAD` + `remote get-url origin`, argv-list, no `shell`, non-interactive env — via shared `_run(argv, error_cls=ScanError)`. Errors → `ScanError`. **Credential-leak check: SAFE.** `_run` reports only the safe subcommand label (`_git_subcommand` skips `git` + `-C <path>`) plus git stderr, never raw argv; scan's argv carries no URL (`remote get-url origin`), and the URL only appears on stdout on success. `test_scan_does_not_leak_credential_url_in_error` asserts `SECRET_URL` absent. Reuses PR-2a's safe-label pattern correctly.

4. **`GitWorkspaceProvider.promote(source, dest, branch)`** — PASS. `git -C <source> worktree add -b <branch> -- <dest>`: argv-list, no `shell`, `--` end-of-options before `dest`, non-interactive env, via `_run(argv, error_cls=PromotionError)`. `source` untouched (locked commit recoverable). `AlreadyUnlockedError` raised when `dest.exists()` BEFORE invoking git (test asserts `calls == []` on re-unlock). Failure → `PromotionError`. See WARNING on adapter-level placement.

5. **Generalized `_run(argv, error_cls=CheckoutError)`** — PASS. Single subprocess chokepoint accepts a caller-supplied `WorkspaceError` subclass so scan/promote raise their own typed errors through the same non-interactive-env + safe-label + FileNotFoundError/TimeoutExpired/nonzero plumbing as checkout. No duplication, no new injection surface, default preserves checkout behavior. (PR-2a's `--` end-of-options SUGGESTION and timeout-branch-test SUGGESTION are both now addressed in this batch.)

6. **Purity** — PASS. `lint-imports` = 4 kept / 0 broken. `materialize_state` and `_match_root_and_layer` are pure core functions; adapter never imported by core.

7. **Tests** — PASS, behavior-first, not tautological. `TestMaterializeState` (4): layout + worktrees precedence (writable commit wins), missing-directory-not-error (empty state), malformed-path raises `ScanError` with `match=<path>`, outside-any-root raises `ScanError` with `match=<path>`. `TestScan` (4): reads HEAD+url skipping non-git siblings, skips non-existent root, corrupted HEAD → `ScanError`, credential-URL not leaked. `TestPromote` (2): worktree add with `-b <branch>` + re-unlock raises `AlreadyUnlockedError` with zero git calls, promote failure → `PromotionError`. Failure paths for scan and promote and materialize_state edge cases all covered.

8. **Scope discipline** — PASS. `git diff --stat main` = exactly `projection.py`, `provider.py`, their two test files, `tasks.md`, `apply-progress.md`. No `forge project`/`forge unlock`/`forge validate` CLI wiring leaked (`main.py` untouched — validate still passes `materialized=None`; real-scan wiring is PR-3). No `factory/` touched (dir absent). No PR-3/PR-4 work leaked.

## Warnings

- **WARNING (test coverage gap, non-blocking)**: The spec scenarios "Fully projected tree materializes clean" and "Missing directory is not an error" explicitly assert on `detect_drift(..., materialized=state)` (`is_clean=True` / `not_materialized`), but no test composes `materialize_state` → `detect_drift`. Both halves are independently tested and the round-trip is verified by trace, but the integration assertion the spec names does not run at runtime. PR-3 (which wires scan→materialize_state→detect_drift into `forge validate`) MUST carry that round-trip test.
- **WARNING (design placement, note for PR-4)**: `AlreadyUnlockedError` is raised in the adapter (`dest.exists()`), whereas the spec attributes the check to the pure core `unlock` use-case. Acceptable for PR-2b — it is a filesystem fact and a dumb-adapter guard, and it does not preclude PR-4's pure `unlock` from short-circuiting earlier via `materialize_state` (worktrees-root entry present → already unlocked). PR-4 must decide whether the core owns this decision or delegates the final race-safe check to the adapter; the current placement is defensible either way.

## Suggestions

- **SUGGESTION**: `test_layout_and_worktrees_precedence` only exercises the worktree entry AFTER the read-only entry in scan order. The impl's two-pass is order-independent, but a companion case with the worktree entry FIRST would triangulate that claim directly.
- **SUGGESTION**: PROCESS — PR-2b changes are UNCOMMITTED in the working tree (`git status` shows 6 modified files). Orchestrator MUST commit before opening the PR.
- **SUGGESTION**: Cosmetic `.marker` sanity assert in the PR-2a checkout test remains weak (carried over, harmless).

## Verdict

PASS WITH WARNINGS. PR-2b fully satisfies its contract with green evidence (129 passed, 4 kept/0 broken). `materialize_state` is genuinely pure and its output exactly satisfies the `detect_drift` matching contract (traced against `state.py`/`drift.py`), finally activating the real lock<->state drift path for PR-3 to wire. `scan` stays dumb, discovers repos bounded, and does NOT leak credentialed URLs in `ScanError` (the PR-2a bug class is not reintroduced). `promote` is argv-list/no-shell/`--`-guarded with correct `AlreadyUnlockedError`/`PromotionError` taxonomy. Zero CRITICAL. Next: commit PR-2b, then sdd-apply PR-3 (which owns the materialize_state<->detect_drift round-trip integration test).
