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
