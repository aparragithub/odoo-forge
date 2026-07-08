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
