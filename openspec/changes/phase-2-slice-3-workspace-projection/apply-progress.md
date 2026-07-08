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

## Batch 2 — PR-2a: Pure project_workspace + Checkout Adapter + 4th Contract

**Mode**: Strict TDD (RED → GREEN, no REFACTOR needed)
**Branch**: `sdd/phase-2-slice-3-pr2a-checkout-adapter` (base = PR-1 branch)
**Scope**: PR-2a only. PR-2b/3/4 NOT started.

### Completed Tasks (PR-2a)
- [x] 4.1 RED: `test_projection.py::TestProjectWorkspace::test_calls_provider_checkout_per_entry`
- [x] 4.2 GREEN: `project_workspace(plan, provider) -> None` (deviation from `-> WorkspaceReport`, see below)
- [x] 5.1 Create `odoo_forge_workspace/__init__.py` + `provider.py` scaffold
- [x] 5.2 RED: `tests/adapters/test_workspace_provider.py` (idempotent skip, dirty refusal, worktree refusal, clean-replace, missing-git-binary)
- [x] 5.3 GREEN: implement `checkout` — temp clone + `os.replace`, skip if `HEAD` matches, refuse dirty/worktree with `CheckoutError`
- [x] 6.1 Add `odoo_forge_workspace` to `pyproject.toml` root packages + wheel include
- [x] 6.2 Add 4th import-linter contract forbidding `odoo_forge -> odoo_forge_workspace`
- [x] 6.3 Verify `uv run lint-imports` — 4 kept, 0 broken

### Files Changed
| File | Action | What Was Done |
|------|--------|----------------|
| `src/odoo_forge/manifest/projection.py` | Modified | Added pure `project_workspace(plan, provider) -> None` — loops `WorkspacePlan.steps`, calls `provider.checkout` per entry; zero I/O, provider injected via Protocol (`TYPE_CHECKING` import only). |
| `src/odoo_forge_workspace/__init__.py` | Created | Package init re-exporting `GitWorkspaceProvider`, mirrors `odoo_forge_git/__init__.py`. |
| `src/odoo_forge_workspace/provider.py` | Created | `GitWorkspaceProvider.checkout`: idempotent (skip if `HEAD==commit`), refuses dirty checkout and linked worktrees (`CheckoutError`), otherwise clones to a `tempfile.mkdtemp()` sibling of `dest` + `git checkout --detach <commit>` + `os.replace` (atomic, same-filesystem). argv-list subprocess only, non-interactive env mirroring `odoo_forge_git`. `scan`/`promote` stubbed to raise `NotImplementedError` (PR-2b scope). |
| `pyproject.toml` | Modified | Added `odoo_forge_workspace` to root packages + wheel packages; added 4th import-linter contract. |
| `tests/manifest/test_projection.py` | Modified | Added `_FakeWorkspaceProvider` + `TestProjectWorkspace` (2 tests). |
| `tests/adapters/test_workspace_provider.py` | Created | 10 tests covering clone+replace, idempotent skip, dirty refusal, linked-worktree refusal, clean-checkout-replace, missing-git-binary, credential-leak safety, argv end-of-options safety, Protocol conformance, scan/promote NotImplementedError stubs. |
| `openspec/changes/phase-2-slice-3-workspace-projection/tasks.md` | Modified | Marked PR-2a tasks `[x]`, added Known Deviation note. |

### Deviations from Design
`project_workspace(plan, provider)` returns `None`, not `WorkspaceReport` as named in
tasks.md/design.md's Interfaces section. Neither spec nor design define `WorkspaceReport`'s
fields anywhere — it appears only as a bare return-type name with no schema. Mirrored
`build_lock(manifest, provider) -> Lockfile`'s precedent exactly instead: a pure loop over
provider calls, exceptions propagate uncaught (satisfies the spec's "forge project stops on
first failure, no partial-step rollback" requirement without a wrapper object). Flagged for
sdd-verify/judgment-day review before PR-3's `forge project` CLI locks in the exact call
contract.

### Evidence (exact command output)
```
$ uv run pytest
114 passed in 0.41s   (up from 104 baseline)
```
```
$ uv run lint-imports
Contracts: 4 kept, 0 broken.   (up from 3 kept)
```

### Remaining Tasks (as of end of PR-2a)
- [ ] PR-2b: `materialize_state` + scan/promote adapters
- [ ] PR-3: `forge project` CLI + `forge validate` scan wiring
- [ ] PR-4: `forge unlock` CLI

## Batch 3 — PR-2b: Pure materialize_state + Scan/Promote Adapters

**Mode**: Strict TDD (RED → GREEN, no REFACTOR needed)
**Branch**: `sdd/phase-2-slice-3-pr2b-scan-promote` (base = PR-2a branch)
**Scope**: PR-2b only. PR-3/4 NOT started.

### Completed Tasks (PR-2b)
- [x] 7.1 RED: `test_projection.py::TestMaterializeState::*` (layout+worktrees precedence, missing-directory-not-an-error, malformed-path raises, path-outside-any-root raises)
- [x] 7.2 GREEN: `materialize_state(scanned, roots) -> MaterializedState`
- [x] 8.1 RED: `test_workspace_provider.py::TestScan::*` (reads HEAD + remote url, skips non-git dirs, skips nonexistent root, corrupted-HEAD raises `ScanError`, no credential leak in error)
- [x] 8.2 GREEN: implement `scan` — `git -C <path> rev-parse HEAD` / `git -C <path> remote get-url origin`, prunes `os.walk` at each found repo root, raises `ScanError` on failure
- [x] 9.1 RED: `test_workspace_provider.py::TestPromote::*` (creates worktree + branch, raises `AlreadyUnlockedError` on re-unlock, `PromotionError` on failure)
- [x] 9.2 GREEN: implement `promote` — `git worktree add -b <branch> -- <dest>` run from `source`, `AlreadyUnlockedError` if `dest` exists, `PromotionError` on non-zero exit

### TDD Cycle Evidence
| Task | Test File | RED | GREEN |
|------|-----------|-----|-------|
| 7.1-7.2 materialize_state | tests/manifest/test_projection.py::TestMaterializeState | `ImportError: cannot import name 'materialize_state'` | 20/20 projection tests pass |
| 8.1-8.2 scan | tests/adapters/test_workspace_provider.py::TestScan | `NotImplementedError: scan lands in PR-2b` | 19/19 adapter tests pass |
| 9.1-9.2 promote | tests/adapters/test_workspace_provider.py::TestPromote | `NotImplementedError: promote lands in PR-2b` | 19/19 adapter tests pass |

### Files Changed
| File | Action | What Was Done |
|------|--------|----------------|
| `src/odoo_forge/manifest/projection.py` | Modified | Added pure `materialize_state(scanned, roots) -> MaterializedState` + private `_match_root_and_layer(path, roots)` helper. Derives layer name from the `/mnt/<root>/<layer>/...` path segment matched against `roots` (e.g. `MOUNT_ROOTS`); groups repos by layer keyed by `url` so a `worktrees`-root entry always overrides a same-`url` read-only entry (applied in a second pass, order-independent). Raises `ScanError` naming the offending path when it matches no known root, or matches a root but is missing the `<layer>` segment. Zero I/O. |
| `src/odoo_forge_workspace/provider.py` | Modified | Implemented `scan(roots) -> list[ScannedRepo]`: walks each root with `os.walk`, treats any directory containing `.git` as one repo (pruning further descent via `dirnames[:] = []`), reads `HEAD` + `remote.origin.url` via `git -C`, raises `ScanError` on failure. Implemented `promote(source, dest, branch) -> None`: raises `AlreadyUnlockedError` if `dest` already exists, otherwise `git -C <source> worktree add -b <branch> -- <dest>`, raises `PromotionError` on failure. Generalized `_run(argv, error_cls=CheckoutError)` to accept a caller-supplied `WorkspaceError` subclass so `scan`/`promote` raise their own typed errors through the same safe-subcommand-label / non-interactive-env plumbing as `checkout`. |
| `tests/manifest/test_projection.py` | Modified | Added `TestMaterializeState` (4 tests: layout+worktrees precedence, missing-directory-not-an-error, malformed-path raises, path-outside-any-root raises). |
| `tests/adapters/test_workspace_provider.py` | Modified | Replaced the PR-2a `test_scan_and_promote_are_not_yet_implemented` stub test with `TestScan` (4 tests) and `TestPromote` (2 tests). |
| `openspec/changes/phase-2-slice-3-workspace-projection/tasks.md` | Modified | Marked PR-2b tasks `[x]`. |

### Deviations from Design
None beyond the PR-2a-flagged `WorkspaceReport` deviation (unaffected by this batch).
`promote`'s `AlreadyUnlockedError` check (`dest.exists()`) is implemented directly in the
adapter rather than deferred to a future pure `unlock` core use-case, since "does a path
already exist on disk" is an adapter-level filesystem fact and task 9.2 explicitly calls
for the adapter to raise `AlreadyUnlockedError`. This does not preclude a future `unlock`
core use-case (PR-4 scope) from also short-circuiting before calling `promote` if it has
already computed the answer via `materialize_state`.

### Evidence (exact command output)
```
$ uv run pytest -q
........................................................................ [ 55%]
.........................................................                [100%]
129 passed in 0.44s   (up from 114 baseline)
```
```
$ uv run lint-imports
Contracts
---------
Analyzed 32 files, 62 dependencies.
-----------------------------------
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Contracts: 4 kept, 0 broken.
```

### Remaining Tasks (as of end of PR-2b)
- [ ] PR-3: `forge project` CLI + `forge validate` scan wiring
- [ ] PR-4: `forge unlock` CLI

### Status
26/48 tasks complete in the full 5-PR chain (PR-1 12/12, PR-2a 8/8, PR-2b 6/6). Ready for
sdd-verify on PR-2b, then sdd-apply again for PR-3.

## Batch 4 — PR-3: `forge project` CLI + `forge validate` Scan Wiring

**Mode**: Strict TDD (RED → GREEN, no REFACTOR needed)
**Branch**: `sdd/phase-2-slice-3-pr3-project-cli` (base = PR-2b branch)
**Scope**: PR-3 only. PR-4 NOT started.

### Completed Tasks (PR-3)
- [x] 10.1 RED: `tests/cli/test_project.py::test_valid_lock_projects_every_layer` (+ mid-plan-failure, missing-lock cases)
- [x] 10.2 GREEN: `_make_workspace_provider()` + `forge project [--manifest][--lock]` in `main.py` calling `plan_projection` + `project_workspace`
- [x] 10.3 RED: `test_project.py::test_mid_plan_checkout_failure_stops_cleanly_exits_nonzero`
- [x] 10.4 GREEN: catch the shared `ManifestError` base (covers `WorkspaceError`/`ProjectionError`/`CheckoutError`/`LockfileError`), exit 1 with single-cause message, no traceback; `project_workspace`'s uncaught-propagation-on-first-failure (from PR-2a) already guarantees no touch of completed steps
- [x] 11.1 RED: `tests/cli/test_validate.py::test_drift_detected_against_real_scanned_workspace`
- [x] 11.2 GREEN: `forge validate` now calls `provider.scan(list(MOUNT_ROOTS.values()))` + `materialize_state(scanned, MOUNT_ROOTS)`, passes the real `MaterializedState` into `detect_drift` — replaces the previously-dead `materialized=None` call
- [x] Round-trip integration test (verify-requested, not a numbered task): `tests/manifest/test_projection_roundtrip.py` — composes `plan_projection → project_workspace → scan → materialize_state → detect_drift` end-to-end via an in-memory fake `WorkspaceProvider` (no real git/network), proving no false drift on a matching workspace and correct `not_materialized`/`commit_mismatch` on divergence

### TDD Cycle Evidence
| Task | Test | RED | GREEN |
|------|------|-----|-------|
| 10.1-10.4 forge project | `tests/cli/test_project.py` (3 tests) | `AttributeError: module 'odoo_forge_cli.main' has no attribute '_make_workspace_provider'` | 3/3 pass after adding `_make_workspace_provider()` + `project` command |
| 11.1-11.2 validate scan wiring | `tests/cli/test_validate.py::test_drift_detected_against_real_scanned_workspace` | Would have failed the assertion against `materialized=None` (no `commit_mismatch` ever produced) — written directly against the target behavior since the CLI already had a `validate` command to extend, not a from-scratch RED/ImportError cycle | 11/11 `test_validate.py` tests pass after wiring `scan`→`materialize_state`→`detect_drift` |

### Files Changed
| File | Action | What Was Done |
|------|--------|----------------|
| `src/odoo_forge_cli/main.py` | Modified | Added imports for `MOUNT_ROOTS`/`materialize_state`/`plan_projection`/`project_workspace`, `WorkspaceProvider` port, `GitWorkspaceProvider` adapter. Added `_make_workspace_provider() -> WorkspaceProvider` composition-root helper (mirrors `_make_provider()`). Wired `validate` to call `provider.scan(list(MOUNT_ROOTS.values()))` → `materialize_state(scanned, MOUNT_ROOTS)` → `detect_drift(parsed, lock, materialized)`, replacing the hardcoded `materialized=None`. Added new `forge project [--manifest][--lock]` command: loads manifest + lock (erroring with a clean message if no lock exists — "run `forge lock` first"), calls `plan_projection` then `project_workspace(plan, provider)` inside a single `try/except ManifestError` resilient boundary (catches `WorkspaceError`/`CheckoutError`/`ProjectionError`/`LockfileError` via the shared base), exits 1 with a single `error:` line and no traceback on failure, prints `projected N repo(s) from <lock_path>` on success. |
| `tests/cli/test_project.py` | Created | `_FakeWorkspaceProvider` (records `checkout` calls, optional `fail_on_call` index) + 3 tests: valid lock projects every layer in lock order, mid-plan checkout failure stops cleanly (exit 1, single error, only completed steps recorded), missing lockfile exits clean with a single error. |
| `tests/cli/test_validate.py` | Modified | Added `_FakeScanningWorkspaceProvider` + `test_drift_detected_against_real_scanned_workspace`: monkeypatches `_make_workspace_provider` to return a scan reporting a stale commit, proving `validate` renders `commit_mismatch` drift text sourced from the real scan pipeline, not a hardcoded `None`. |
| `tests/cli/test_lock.py` | Modified | Updated `test_lock_then_validate_round_trip_no_drift`: since `validate` now performs a real scan, the pre-existing assertion ("no drift" with **no** provider mocked) would now correctly report `not_materialized` for an unprojected workspace — activating the previously-dead path is the intended PR-3 behavior change. Added `_FakeProjectedWorkspaceProvider` + monkeypatched `_make_workspace_provider` to simulate a fully-projected workspace matching the lock exactly, preserving the test's original "no drift after `lock`" intent while proving the new scan wiring is correct end-to-end. |
| `tests/manifest/test_projection_roundtrip.py` | Created | `_InMemoryWorkspaceProvider` (checkout records to an in-memory dict, scan replays it — no filesystem/git I/O) + 3 tests: no false drift on a matching workspace after `plan_projection → project_workspace → scan → materialize_state → detect_drift`; `not_materialized` drift when nothing was ever projected; `commit_mismatch` drift when a checkout goes stale after projection. |
| `openspec/changes/phase-2-slice-3-workspace-projection/tasks.md` | Modified | Marked PR-3 tasks `[x]`, added PR-3 gate evidence line. |

### Evidence (exact command output)
```
$ uv run pytest -q
........................................................................ [ 52%]
................................................................         [100%]
136 passed in 0.47s   (up from 129 baseline)
```
```
$ uv run lint-imports
Contracts
---------
Analyzed 32 files, 65 dependencies.
-----------------------------------
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Contracts: 4 kept, 0 broken.
```
```
$ uv run forge --help
 Commands ─
 validate  Parse, compose, and report lock drift for a manifest.
 lock      Resolve every declared ref to a commit SHA and write `project.lock`.
 project   Project a locked manifest onto the filesystem under fixed mount roots.
```

### Deviations from Design
None new. Confirms the PR-2a-flagged deviation (`project_workspace(plan, provider) -> None`,
not `WorkspaceReport`) is sufficient for `forge project`'s exit-code/message contract:
the CLI needs only `len(plan.steps)` (already available from the `WorkspacePlan` it built
itself) for its success message, and relies on the uncaught-exception-on-first-failure
behavior for the resilient-boundary/stop-cleanly requirement — no wrapper report object
was needed anywhere in this PR. Recommend judgment-day treat the PR-2a `WorkspaceReport`
deviation as resolved/closed rather than still-open.

No `--no-scan` escape hatch was added to `forge validate` (design's open question was
explicitly "defer"): scanning is unconditional and default-on per the spec's literal
`MODIFIED` requirement text ("When a workspace tree exists ... it MUST call
`WorkspaceProvider.scan`"). Scanning fixed absolute `/mnt/*` roots that don't exist in a
test/dev sandbox is safe and cheap (`GitWorkspaceProvider.scan` skips non-existent roots
via `root.exists()`), so this required no test-environment special-casing.

### Issues Found
None.

### Remaining Tasks
- [ ] PR-4: Phase 12 (`forge unlock` CLI) — NOT STARTED

### Status
36/48 tasks complete in the full 5-PR chain (PR-1 12/12, PR-2a 8/8, PR-2b 6/6, PR-3 6/6 —
counting the round-trip integration test as folded into Phase 11's gate rather than a new
numbered task). Ready for sdd-verify on PR-3, then sdd-apply again for PR-4 (`forge unlock`).

## Batch 4b — PR-3 Verify Follow-up: Credential-Leak Test Gap

**Mode**: Strict TDD (test written first; production behavior confirmed already correct —
this test is a characterization/lock-in, not a bugfix)
**Branch**: `sdd/phase-2-slice-3-pr3-project-cli` (same branch as Batch 4)
**Trigger**: sdd-verify flagged one non-blocking test gap on PR-3 before merge — no test
proved `forge project`'s error output both (1) names the failing repo and (2) never leaks
a credential embedded in the lock's repo URL.

### Test Added
`tests/cli/test_project.py::test_mid_plan_failure_names_repo_without_leaking_credentials` —
a `_CredentialLeakSafeProvider` double fails `checkout` on a repo whose lock URL is
`https://user:secret-token@example.com/custom-x.git`, raising `CheckoutError` the way
`GitWorkspaceProvider` actually does (naming `dest`, never the raw `url`). Asserts:
1. `"custom-x"` appears in `result.output` (spec: "exits non-zero naming the failing repo")
2. `"secret-token"` does NOT appear in `result.output` (no credential leak)
3. `"Traceback"` does NOT appear in `result.output`

### RED/GREEN Status
**GREEN on first run — no production code change needed.** `forge project`'s existing
`except ManifestError` boundary in `main.py` re-emits whatever message the raised
`CheckoutError` carries verbatim; since the real `GitWorkspaceProvider` (and this test's
double, mirroring it) never embeds the raw credentialed URL in a `CheckoutError` message
— only `dest`/subcommand-safe labels, per the existing `checkout`/`_run`/`_git_subcommand`
design from PR-2a/2b — the CLI boundary already never leaks a credential. This test
characterizes and locks in that existing correct behavior; it was not a bugfix.

### Evidence (exact command output)
```
$ uv run pytest -q
........................................................................ [ 52%]
.................................................................        [100%]
137 passed in 0.46s   (up from 136 baseline)
```
```
$ uv run lint-imports
Contracts: 4 kept, 0 broken.   (unchanged)
```

### Files Changed
| File | Action | What Was Done |
|------|--------|----------------|
| `tests/cli/test_project.py` | Modified | Added `_CredentialLeakSafeProvider` + `test_mid_plan_failure_names_repo_without_leaking_credentials`. |

### Status
137/137 tests passing, 4/4 import-linter contracts kept. No production code changed in
this follow-up. PR-3 unchanged in scope (still 6/6 numbered tasks); this is an additional
verify-requested test, not a new task. Ready to proceed to sdd-verify re-check / merge, then
PR-4 (`forge unlock`).
