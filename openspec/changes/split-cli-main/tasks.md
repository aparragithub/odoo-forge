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

- [ ] 1.1 RED: run `uv run pytest tests/test_mount_base.py -v` to confirm current `from main import _resolve_mount_base` passes pre-move (baseline).
- [ ] 1.2 Create `src/odoo_forge_cli/_composition.py`; move `_make_provider`, `_make_published_artifact_resolver`, `_make_workspace_provider`, `_make_manifest_workspace_provider`, `_make_backend_provider`, `_make_image_registry_provider`, `_doctor_age_key_file`, `GitWorkspaceProvider` import.
- [ ] 1.3 Create `src/odoo_forge_cli/_presentation.py`; move `_format_drift`, `_format_missing_dependencies`, `_render_validation_errors`.
- [ ] 1.4 Create `src/odoo_forge_cli/_support.py`; move `_resolve_mount_base`, `_host_roots`, `_read_manifest_data`, `_load_lock`, `_write_lock_atomic`, `_check_module_dependencies`.
- [ ] 1.5 Update `main.py` call sites to module-qualified access (`_composition.make_backend_provider(...)`, not bare-name import), per design's module-qualified helper decision.
- [ ] 1.6 Repoint `tests/test_mount_base.py`: `from main import _resolve_mount_base` → `from _support import resolve_mount_base`.
- [ ] 1.7 Repoint `tests/test_lock.py` direct calls (lines ~297, 311) `main._load_lock(...)` → `_support._load_lock(...)`.
- [ ] 1.8 Repoint any `main._make_provider`/`main._make_published_artifact_resolver`/`main._make_enterprise_credential_resolver` patches touched by this slice to `_composition.*`.
- [ ] 1.9 GREEN: run full suite `uv run pytest`; confirm no `main.<moved-symbol>` patch targets remain unresolved.
- [ ] 1.10 REFACTOR: remove now-dead imports from `main.py`; verify no re-export facade exists.
- [ ] 1.11 Verify: `forge --help` unchanged output; `uv run lint-imports` passes; import smoke test for the 3 new modules (no cycle).

## PR2: `commands/image.py`

- [ ] 2.1 RED: run `uv run pytest tests/test_image_registry.py -v` pre-move (baseline).
- [ ] 2.2 Create `src/odoo_forge_cli/commands/image.py`; move `image_resolve`, `image_publish`, `image_pull`, `image_exists`; add `def register(app: typer.Typer) -> None` binding all four via `app.command(name=...)`.
- [ ] 2.3 In `main.py`, import `commands.image` and call `register(app)`; remove the four command bodies.
- [ ] 2.4 Repoint `tests/test_image_registry.py`: `main._make_image_registry_provider` → `_composition.make_image_registry_provider`; `main._make_backend_provider` (l.261) → `_composition.make_backend_provider`.
- [ ] 2.5 GREEN: `uv run pytest` full suite green.
- [ ] 2.6 REFACTOR: confirm `commands/image.py` imports helper modules only (no `from odoo_forge_cli.main import ...`).
- [ ] 2.7 Verify: `forge image-resolve/-publish/-pull/-exists --help` byte-identical; `uv run lint-imports` passes; no cycle.

## PR3: `commands/maintenance.py`

- [ ] 3.1 RED: run `uv run pytest tests/test_doctor.py tests/test_rotate_enterprise_credential.py -v` pre-move (baseline).
- [ ] 3.2 Create `src/odoo_forge_cli/commands/maintenance.py`; move `doctor`, `rotate_enterprise_credential`; add `register(app)`.
- [ ] 3.3 In `main.py`, import `commands.maintenance` and call `register(app)`; remove the two command bodies.
- [ ] 3.4 Repoint `tests/test_doctor.py`: `main._doctor_age_key_file` → `_composition.doctor_age_key_file`; `main._make_enterprise_credential_resolver` → `commands.maintenance.make_enterprise_credential_resolver` (or `ec` module per its owning location).
- [ ] 3.5 Confirm `tests/test_rotate_enterprise_credential.py` needs no change (patches `subprocess.run`; only imports `app`).
- [ ] 3.6 GREEN: `uv run pytest` full suite green.
- [ ] 3.7 Verify: `forge doctor/rotate-enterprise-credential --help` unchanged; `uv run lint-imports` passes; no cycle.

## PR4: `commands/backend.py` (heaviest monkeypatch surface)

- [ ] 4.1 RED: run `uv run pytest tests/test_backend.py -v` pre-move (baseline); enumerate all current `main.*` patch targets in this file.
- [ ] 4.2 Create `src/odoo_forge_cli/commands/backend.py`; move `run`, `status`, `_derive_ref`, `stop`, `logs`, `exec_`; add `register(app)`.
- [ ] 4.3 In `main.py`, import `commands.backend` and call `register(app)`; remove the five command bodies + `_derive_ref`.
- [ ] 4.4 Repoint `tests/test_backend.py`: `main._make_workspace_provider`/`main._make_backend_provider` → `_composition.*`; `main._resolve_mount_base` → `_support.resolve_mount_base`; `main.plan_backend` (l.320) and `from main import plan_backend` (l.29) → `commands.backend.plan_backend`; direct `main._make_backend_provider()` call (l.337) → `_composition.make_backend_provider()`.
- [ ] 4.5 GREEN: `uv run pytest` full suite green; explicitly re-run `tests/test_backend.py -v` to confirm every repointed patch actually intercepts (not silently no-op).
- [ ] 4.6 REFACTOR: confirm `commands/backend.py` size stays ≤~250 lines per design constraint.
- [ ] 4.7 Verify: `forge run/status/stop/logs/exec --help` byte-identical; `uv run lint-imports` passes; no cycle.

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
