# Tasks: Split `odoo_forge_cli/main.py` by responsibility

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~350-420 / PR2 ~150-200 / PR3 ~120-160 / PR4 ~350-420 / PR5a ~200-250 / PR5b ~250-320 |
| 400-line budget risk | Medium (PR1, PR4 near budget; PR5 original scope High → resolved by PR5a/PR5b split) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5a → PR5b (6 PRs, stacked to main) |
| Delivery strategy | force-chained |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

Each PR merges to `main` before the next starts (stacked-to-main). Full suite
+ `lint-imports` green before advancing. No facade re-exports at any stage
(spec: "Monkeypatch and Import Targets Are Repointed, Not Facaded").

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Extract `_composition.py`/`_presentation.py`/`_support.py` | PR1 | `uv run pytest tests/ -k "mount_base or lock or doctor"` | `forge --help` + `uv run lint-imports` | revert PR1 merge commit; `main.py` reverts to pre-split helpers |
| 2 | `commands/image.py` | PR2 | `uv run pytest tests/test_image_registry.py -v` | `forge image-resolve --help` | revert PR2 merge commit only |
| 3 | `commands/maintenance.py` | PR3 | `uv run pytest tests/test_doctor.py tests/test_rotate_enterprise_credential.py -v` | `forge doctor --help` | revert PR3 merge commit only |
| 4 | `commands/backend.py` | PR4 | `uv run pytest tests/test_backend.py -v` | `forge run --help`, `forge status --help` | revert PR4 merge commit only |
| 5a | `commands/manifest.py` (validate/onboard) | PR5a | `uv run pytest tests/test_validate.py tests/test_onboard.py -v` | `forge validate --help`, `forge onboard --help` | revert PR5a merge commit only |
| 5b | `commands/manifest.py` (lock/unlock/project) + thin `main.py` | PR5b | `uv run pytest tests/test_lock.py tests/test_unlock.py tests/test_project.py tests/test_enterprise_credential.py -v` | `forge lock --help`, `forge project --help`, full `forge --help` | revert PR5b merge commit; `main.py` reverts to pre-thinning state |

## PR1: `_composition.py` + `_presentation.py` + `_support.py`

- [x] 1.1 RED: run `uv run pytest tests/test_mount_base.py -v` to confirm current `from main import _resolve_mount_base` passes pre-move (baseline).
- [x] 1.2 Create `src/odoo_forge_cli/_composition.py`; move `_make_provider`, `_make_published_artifact_resolver`, `_make_workspace_provider`, `_make_manifest_workspace_provider`, `_make_backend_provider`, `_make_image_registry_provider`, `_doctor_age_key_file`, `GitWorkspaceProvider` import.
- [x] 1.3 Create `src/odoo_forge_cli/_presentation.py`; move `_format_drift`, `_format_missing_dependencies`, `_render_validation_errors`.
- [x] 1.4 Create `src/odoo_forge_cli/_support.py`; move `_resolve_mount_base`, `_host_roots`, `_read_manifest_data`, `_load_lock`, `_write_lock_atomic`, `_check_module_dependencies`.
- [x] 1.5 Update `main.py` call sites to module-qualified access (`_composition._make_backend_provider(...)`, not bare-name import), per design's module-qualified helper decision. Applied uniformly to ALL 16 command bodies remaining in `main.py` (not just `lock`), since each moved symbol now has exactly one canonical patch target.
- [x] 1.6 Repoint `tests/test_mount_base.py`: `from main import _resolve_mount_base` → `from odoo_forge_cli import _support` + `_support._resolve_mount_base(...)` (kept the leading underscore for consistency with every other repoint in this PR and with PR4's own test inventory row for the same symbol — see Risks in apply-progress for the literal `resolve_mount_base` vs `_resolve_mount_base` naming deviation).
- [x] 1.7 Repoint `tests/test_lock.py` direct calls (lines ~297, 311) `main._load_lock(...)` → `_support._load_lock(...)`.
- [x] 1.8 Repoint any `main._make_provider`/`main._make_published_artifact_resolver`/`main._make_enterprise_credential_resolver` patches touched by this slice to `_composition.*`. Scope was widened beyond `test_lock.py`: since 1.5 qualifies every command's call sites, ALL test files patching a PR1-moved symbol needed repointing (test_lock, test_doctor, test_backend, test_validate, test_onboard, test_unlock, test_project, test_image_registry, test_enterprise_credential). `main._make_enterprise_credential_resolver` patches were left untouched — that symbol belongs to `enterprise_credential.py` (`ec`) and is out of PR1's scope.
- [x] 1.9 GREEN: run full suite `uv run pytest`; confirm no `main.<moved-symbol>` patch targets remain unresolved. Result: 901 passed, 17 deselected (docker-daemon-integration tests, pre-existing marker exclusion), 0 failed.
- [x] 1.10 REFACTOR: remove now-dead imports from `main.py`; verify no re-export facade exists. Dropped `os`, `json`, `tempfile`, `yaml`, `Lockfile`, `ManifestInputError`, `ModuleDependencyError`, `build_mount_roots`, `ordered_addons_roots`, `build_module_index`, `find_missing_dependencies`, `GitWorkspaceProvider`, `DriftEntry` from `main.py` (all now used only inside the new modules). The existing `__all__` block (ec symbols) is untouched — that's PR5b scope per the design's migration table, unrelated to this PR's 3 new modules.
- [x] 1.11 Verify: `forge --help` unchanged output; `uv run lint-imports` passes; import smoke test for the 3 new modules (no cycle). All confirmed — see apply-progress.md for exact output.

## PR2: `commands/image.py`

- [x] 2.1 RED: run `uv run pytest tests/test_image_registry.py -v` pre-move (baseline). Result: 19 passed.
- [x] 2.2 Create `src/odoo_forge_cli/commands/image.py`; move `image_resolve`, `image_publish`, `image_pull`, `image_exists`; add `def register(app: typer.Typer) -> None` binding all four via `app.command(name=...)`.
- [x] 2.3 In `main.py`, import `commands.image` and call `register(app)`; remove the four command bodies.
- [x] 2.4 Repoint `tests/test_image_registry.py`: `main._make_image_registry_provider` → `_composition.make_image_registry_provider`; `main._make_backend_provider` (l.261) → `_composition.make_backend_provider`. Already satisfied by PR1's wider module-qualification scope (task 1.8) — the test already patches `_composition._make_image_registry_provider`/`_composition._make_backend_provider`, which remain the correct canonical targets since `commands/image.py` calls them module-qualified from `_composition`. No further edit needed; verified both patches still intercept (test green).
- [x] 2.5 GREEN: `uv run pytest` full suite green. Result: 901 passed, 17 deselected (unchanged from PR1 baseline).
- [x] 2.6 REFACTOR: confirm `commands/image.py` imports helper modules only (no `from odoo_forge_cli.main import ...`). Confirmed via `rg`.
- [x] 2.7 Verify: `forge image-resolve/-publish/-pull/-exists --help` byte-identical; `uv run lint-imports` passes; no cycle.

## PR3: `commands/maintenance.py`

- [x] 3.1 RED: run `uv run pytest tests/test_doctor.py tests/test_rotate_enterprise_credential.py -v` pre-move (baseline). Post-move but pre-repoint run confirmed the expected failure mode: 2 of 5 `test_doctor.py` tests failed (`test_doctor_fails_and_reports_missing_age_key`, `test_doctor_reports_success_on_both_checks`) because `doctor`'s call site now resolves `_make_enterprise_credential_resolver` against `commands.maintenance`'s globals, not `main`'s — confirming the `main._make_enterprise_credential_resolver` patch had silently gone stale, exactly as the module-qualified-access decision predicts.
- [x] 3.2 Create `src/odoo_forge_cli/commands/maintenance.py`; move `doctor`, `rotate_enterprise_credential`; add `register(app)`.
- [x] 3.3 In `main.py`, import `commands.maintenance` and call `register(app)`; remove the two command bodies.
- [x] 3.4 Repoint `tests/test_doctor.py`: `_composition._doctor_age_key_file` patch target unchanged (already `_composition`-qualified since PR1); `main._make_enterprise_credential_resolver` → `enterprise_credential._make_enterprise_credential_resolver` (the symbol's owning/definition module — `commands/maintenance.py` imports `enterprise_credential` module-qualified, so this is the one canonical patch target, per the design's rule that a helper's definition module is always correct regardless of which command module calls it).
- [x] 3.5 Confirm `tests/test_rotate_enterprise_credential.py` needs no change (patches `subprocess.run`; only imports `app`). Confirmed unchanged — all 2 tests passed unmodified.
- [x] 3.6 GREEN: `uv run pytest` full suite green. Result: 901 passed, 17 deselected (unchanged from PR2 baseline).
- [x] 3.7 Verify: `forge doctor/rotate-enterprise-credential --help` unchanged; `uv run lint-imports` passes; no cycle.

## PR4: `commands/backend.py` (heaviest monkeypatch surface)

- [x] 4.1 RED: run `uv run pytest tests/test_backend.py -v` pre-move (baseline); enumerate all current `main.*` patch targets in this file. Result: 39 passed pre-move. `main.*` patch targets already narrowed by PR1's wide qualification (task 1.8) to `_composition._make_workspace_provider`/`_composition._make_backend_provider`/`_support._resolve_mount_base` (all already correct); the two remaining live `main.*` references were `from odoo_forge_cli.main import plan_backend as original_plan_backend` (import) and `monkeypatch.setattr(main, "plan_backend", ...)` (patch) — both due to move in this PR.
- [x] 4.2 Create `src/odoo_forge_cli/commands/backend.py`; move `run`, `status`, `_derive_ref`, `stop`, `logs`, `exec_`; add `register(app)`.
- [x] 4.3 In `main.py`, import `commands.backend` and call `register(app)`; remove the five command bodies + `_derive_ref`.
- [x] 4.4 Repoint `tests/test_backend.py`: `main._make_workspace_provider`/`main._make_backend_provider` already `_composition.*` (satisfied by PR1's task 1.8, verified unchanged); `main._resolve_mount_base` already `_support._resolve_mount_base` (satisfied by PR1, verified unchanged); `main.plan_backend`/`from main import plan_backend` → repointed to `commands.backend.plan_backend` (bare-imported inside `backend.py`, so the call-site lookup and canonical patch target is `odoo_forge_cli.commands.backend.plan_backend`); no separate direct `main._make_backend_provider()` call existed at the time of this PR (already qualified to `_composition` in PR1).
- [x] 4.5 GREEN: `uv run pytest` full suite green; explicitly re-run `tests/test_backend.py -v` — 39 passed, confirming every repointed patch actually intercepts. Adversarial check: retargeting the `plan_backend` patch to a wrong module (`_composition`) raised `AttributeError: <module ... _composition> has no attribute 'plan_backend'` — proving `monkeypatch.setattr`'s default `raising=True` makes a wrong target fail loud rather than silently no-op, confirming the correct target genuinely binds the real call-site object.
- [x] 4.6 REFACTOR: confirm `commands/backend.py` size stays ≤~250 lines per design constraint. Result: exactly 250 lines (`wc -l`).
- [x] 4.7 Verify: `forge run/status/stop/logs/exec --help` byte-identical (same options, same help text, same defaults); `uv run lint-imports` passes (108 files, 349 dependencies, 6/6 contracts kept); no cycle (`import odoo_forge_cli.commands.backend; import odoo_forge_cli.main` succeeds).

## PR5a: `commands/manifest.py` — validate + onboard

- [ ] 5a.1 RED: run `uv run pytest tests/test_validate.py tests/test_onboard.py -v` pre-move (baseline).
- [ ] 5a.2 Create `src/odoo_forge_cli/commands/manifest.py`; move `validate`, `onboard`; add `register(app)` (extended in PR5b).
- [ ] 5a.3 In `main.py`, import `commands.manifest` and call `register(app)`; remove `validate`/`onboard` bodies.
- [ ] 5a.4 Repoint `tests/test_validate.py`: `main._resolve_mount_base` → `_support.resolve_mount_base`; `main._make_workspace_provider` → `_composition.make_workspace_provider`.
- [ ] 5a.5 Repoint `tests/test_onboard.py`: same targets, including direct call at l.45 → `_support.resolve_mount_base(...)`.
- [ ] 5a.6 GREEN: `uv run pytest` full suite green.
- [ ] 5a.7 Verify: `forge validate/onboard --help` unchanged; `uv run lint-imports` passes; no cycle.

## PR5b: `commands/manifest.py` — lock/unlock/project + thin `main.py`

- [ ] 5b.1 RED: run `uv run pytest tests/test_lock.py tests/test_unlock.py tests/test_project.py tests/test_enterprise_credential.py -v` pre-move (baseline).
- [ ] 5b.2 Move `lock`, `project`, `unlock` into `commands/manifest.py`; extend `register(app)` to bind all five manifest commands.
- [ ] 5b.3 In `main.py`, remove `lock`/`project`/`unlock` bodies; drop the `__all__` re-export block (890-896) — no facade.
- [ ] 5b.4 Repoint `tests/test_lock.py`: `main._make_provider`/`main._make_published_artifact_resolver`/`main._make_enterprise_credential_resolver` → `_composition.*`; direct `main._load_lock` calls (l.297, 311) already repointed in PR1 — confirm no regression.
- [ ] 5b.5 Repoint `tests/test_project.py`: `main._make_workspace_provider`/`main._resolve_mount_base` → `_composition`/`_support`; `setitem(main.__dict__, "GitWorkspaceProvider", ...)` (l.276) → target `_composition.__dict__`.
- [ ] 5b.6 Repoint `tests/test_unlock.py`: `main._make_workspace_provider`/`main._resolve_mount_base` → `_composition`/`_support`.
- [ ] 5b.7 Repoint `tests/test_enterprise_credential.py`: `main._make_provider`/`_make_workspace_provider`/`_make_enterprise_credential_resolver` → `_composition.*`; `main._bind_*` direct → `ec._bind_*` (unchanged import).
- [ ] 5b.8 GREEN: `uv run pytest` full suite green.
- [ ] 5b.9 REFACTOR: confirm `main.py` ≤ ~80 lines, containing only `app`, `@app.callback`, and `register(app)` calls; confirm no module exceeds ~250 lines.
- [ ] 5b.10 Verify (final): full `CliRunner` suite green unmodified in assertions; `forge --help` and every subcommand `--help` byte-identical to pre-split baseline; `forge` entry point (`odoo_forge_cli.main:app`) resolves; `uv run lint-imports` passes with `forbidden_modules=["odoo_forge_cli"]`; no circular imports across all `commands/*` + helper modules.
