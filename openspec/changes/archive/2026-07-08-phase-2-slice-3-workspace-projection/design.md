# Design: Phase 2 Slice 3 — Workspace Projection

## Technical Approach
First filesystem projection. `odoo_forge` stays import-pure: planning + mapping + state assembly are pure functions; a new `WorkspaceProvider` port (`ports/workspace_provider.py`, mirroring `ports/source_provider.py`) abstracts all git/fs I/O; the concrete adapter lives in a NEW sibling package `odoo_forge_workspace`; `odoo_forge_cli` is the composition root. A 4th import-linter contract forbids `odoo_forge -> odoo_forge_workspace`. Planning is pure and PROVIDER-FREE (the lock already carries commits — no network needed), unlike `build_lock`; the port is only used to EXECUTE plans and scan disk. Activates the dead `detect_drift(..., materialized=None)` path (`main.py:144`) by feeding a real scan. Likely chained PRs (see forecast note).

## Architecture Decisions

| # | Decision | Choice | Rejected | Rationale |
|---|----------|--------|----------|-----------|
| 1 | `plan_projection` placement | Pure `plan_projection(manifest, lock) -> WorkspacePlan` in new `manifest/projection.py`; no provider param | provider-injected (like `build_lock`); CLI-side | lock already has commits → planning needs zero I/O; provider only executes/scans |
| 2 | Layer→root classification | Additive **optional** `category: Literal["custom","community","localization","enterprise"] \| None = None` on `GitLayer`/`PublishedLayer`; precedence: explicit `category` > convention (`requires_edition=="enterprise"`→enterprise; core→community; else custom); join manifest↔lock by `.name` | add role to LOCK (`ResolvedLayer`); free-text `Layer.name` guess | lock format UNCHANGED → archived 2a/2b locks still validate; optional field → archived `project.yaml` specs still parse; back-compat preserved |
| 3 | `unlock` mechanism | `git worktree add /mnt/worktrees/<layer>/<repo>` on new branch from locked commit; **repo granularity** | branch-in-place in the projected dir | keeps read-only projection pristine (detached HEAD at locked commit); `/mnt/worktrees` is scanned FIRST by `entrypoint.sh` → writable copy wins addons_path precedence; non-destructive, reversible |
| 4 | Scan → `MaterializedState` | Adapter `scan(roots)->list[ScannedRepo{path,url,commit}]` (raw: `git -C rev-parse HEAD` + `remote.origin.url`); pure core `materialize_state(scanned, roots)` derives `layer` from `/mnt/<root>/<layer>/...` path segment, applies worktrees-first precedence dedup | adapter returns `MaterializedState` directly (buries layout+precedence convention in adapter) | keeps layout/precedence logic PURE + unit-testable without git; `MaterializedRepo.url`/`MaterializedLayer.name` reproduce lock `.url`/`.name` exactly → `detect_drift` matches (verified vs `state.py`/`drift.py`) |
| 5 | Execution use-case | Pure `project_workspace(plan, provider: WorkspaceProvider) -> WorkspaceReport` in core (loop over plan, call port) | loop inline in CLI | mirrors `build_lock` shape; fakeable seam; CLI stays thin |
| 6 | Error home | New `WorkspaceError` family in `manifest/errors.py` (message-only, pure): `CheckoutError`, `ScanError`, `PromotionError` | subclass `ManifestError`/`ResolutionError` | distinct catch at CLI boundary; separate family per Slice-1/2b precedent |
| 7 | 4th contract | ADD forbidden `odoo_forge`→`odoo_forge_workspace` (3→4 kept); add pkg to `root_packages` + wheel | weaken existing | deny-list is per-source; adapter freely imports git/subprocess + core domain (allowed direction) |

## Data Flow

    project.yaml + project.lock ─(CLI)→ Manifest, Lockfile
         │  plan_projection(manifest, lock)            [core, pure]
         ▼  WorkspacePlan[ (layer, repo url, commit, root, dest) ]
    project_workspace(plan, provider)                  [core use-case]
         │   provider.checkout(url, commit, dest)      [odoo_forge_workspace: temp clone + os.replace]
         ▼
    /mnt/{community,custom,localization,enterprise}/<layer>/<repo>   (detached HEAD @ commit)
         │  forge validate: provider.scan(ROOTS) → materialize_state(...)
         ▼  MaterializedState → detect_drift(manifest, lock, state)   [was None]
    unlock <layer>: provider.promote(src, /mnt/worktrees/<layer>/<repo>, branch)  [git worktree]

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge/manifest/projection.py` | Create | `WorkspacePlan`, `WorkspacePlanEntry`, `ScannedRepo`, `MOUNT_ROOTS`, `plan_projection`, `project_workspace`, `materialize_state`, `classify_root` |
| `src/odoo_forge/ports/workspace_provider.py` | Create | `@runtime_checkable WorkspaceProvider` Protocol (`checkout`/`scan`/`promote`) |
| `src/odoo_forge/manifest/schema.py` | Modify | additive optional `category` on `GitLayer`/`PublishedLayer` |
| `src/odoo_forge/manifest/errors.py` | Modify | `WorkspaceError`+`CheckoutError`/`ScanError`/`PromotionError` |
| `src/odoo_forge_workspace/{__init__,provider}.py` | Create | `GitWorkspaceProvider`: clone/checkout, rev-parse scan, `git worktree` promote |
| `src/odoo_forge_cli/main.py` | Modify | `forge project` + `forge unlock` cmds; `_make_workspace_provider()`; wire scan into `validate` |
| `pyproject.toml` | Modify | 4th contract; add pkg to `root_packages` + wheel |

## Interfaces
```python
# ports/workspace_provider.py
@runtime_checkable
class WorkspaceProvider(Protocol):
    def checkout(self, url: str, commit: str, dest: Path) -> None: ...
    def scan(self, roots: Sequence[Path]) -> list[ScannedRepo]: ...
    def promote(self, source: Path, dest: Path, branch: str) -> None: ...
# manifest/projection.py (pure)
def plan_projection(manifest: Manifest, lock: Lockfile) -> WorkspacePlan: ...
def project_workspace(plan: WorkspacePlan, provider: WorkspaceProvider) -> WorkspaceReport: ...
def materialize_state(scanned: list[ScannedRepo], roots: Sequence[Path]) -> MaterializedState: ...
```

## Filesystem Safety
Per-repo atomic (temp clone + `os.replace`); idempotent (HEAD==commit → no-op). Existing dir: correct commit→skip; wrong commit & clean→fetch+checkout; DIRTY or is-a-worktree→`CheckoutError`, never destroy. Projection targets read-only roots ONLY; `/mnt/worktrees` is created/removed solely by `unlock`, which refuses when the worktree has uncommitted changes. Whole-tree atomicity across repos is NOT guaranteed — mitigated by resumable idempotent projection + truthful scan.

## Testing Strategy (Strict TDD)
| Layer | What | How |
|-------|------|-----|
| Unit pure | `plan_projection` root mapping (category precedence, core→community, enterprise, localization, default custom, manifest↔lock join by name); `materialize_state` layout+worktrees-precedence dedup; `project_workspace` calls port per entry | fake `WorkspaceProvider` (in-memory dict), no git/network |
| Unit adapter | checkout idempotency/dirty-refusal; scan rev-parse/remote-url; worktree promote | monkeypatch `subprocess.run` + `tmp_path` |
| CLI | `validate` passes real state to `detect_drift`; `project` idempotency; `unlock` | `CliRunner` + monkeypatched `_make_workspace_provider` |
| Arch | 4 contracts kept/0 broken; core imports zero git/subprocess; adapter unimportable from core | import-linter CI |

## Migration / Rollout
No migration. Additive package + commands + optional schema field; lock format unchanged. Revert branch(es) to roll back.

## Open Questions
- [ ] Command names: `forge project` / `forge unlock` (confirm vs `materialize`/`sync`).
- [ ] `validate` scanning unprojected roots surfaces `not_materialized` drift (intended activation) — add `--no-scan` escape hatch? Recommend defer.
- [ ] Deferred debt: retry/backoff/observability on checkout; auth/network reuse of `ResolutionError` during clone; override application (RE-DEFERRED). Recommend keep deferred.
