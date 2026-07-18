## Verification Report — configurable-mount-base

**Verdict: PASS WITH WARNINGS**

### Completeness
- `tasks.md`: 19/19 tasks checked (Phase 1: 1.1–1.7, Phase 2: 2.1–2.8, Phase 3: 3.1–3.4).
- All checked tasks confirmed against real code and passing tests (no rubber-stamped checkboxes found).
- `apply-progress` (Engram #8873) documents scope, files touched, one authorized deviation
  (task 2.6 named `tests/cli/test_lock.py` by mistake; the actual `project`-command tests
  live in `tests/cli/test_project.py`, which is what was extended — verified correct).
- Diff size: 364 changed lines across 2 source files + 7 test files (`git diff --stat` against
  parent of `92234ae`). Within forecast (~150-250 estimate, extended by new test files), under
  the 400-line review budget. Low risk confirmed.

### Test/Build Evidence
- `uv run pytest -q` → **697 passed, 14 deselected** (matches apply-progress claim exactly).
- `uv run mypy src/odoo_forge/manifest/projection.py src/odoo_forge_cli/main.py` → **Success: no issues found in 2 source files**.
- `uv run lint-imports` → **6 contracts kept, 0 broken** (Core never imports infra/CLI/git/workspace/docker/registry adapters — all held).
- `uv run ruff check .` → **All checks passed**.
- `uv run ruff format --check .` → **1 file would be reformatted** (`src/odoo_forge/manifest/projection.py`, two long-line joins around `container_paths`/`MountEvidence.container_path` construction) — cosmetic only, not caught by task 3.x checklist. WARNING, non-blocking.
- `rg 'os\.environ|os\.getenv' src/odoo_forge/` → **zero matches** — core purity confirmed independently (not just trusted from apply-progress).

### Specification Compliance (spec: `openspec/changes/configurable-mount-base/specs/manifest/spec.md`)

| Scenario | Covering test | Result |
|---|---|---|
| Default resolution with no env vars set → `~/.local/state/odoo-forge` | `tests/cli/test_mount_base.py::TestResolveMountBase::test_default_resolution_with_no_env_vars_set` | PASS |
| `FORGE_MOUNT_BASE` overrides everything (even with `XDG_STATE_HOME` set) | `...::test_forge_mount_base_overrides_everything` | PASS |
| `XDG_STATE_HOME` influences the default when `FORGE_MOUNT_BASE` unset | `...::test_xdg_state_home_influences_the_default` | PASS |
| Backward compatibility: `FORGE_MOUNT_BASE=/mnt` reproduces pre-change `/mnt/*` host paths exactly | `...::test_forge_mount_base_mnt_reproduces_the_pre_change_host_paths` (asserts `build_mount_roots(_resolve_mount_base()) == MOUNT_ROOTS`) | PASS |
| Host and container mount root tables decoupled — 5 keys derive as `<base>/<root>` | `tests/manifest/test_projection.py` (`test_build_mount_roots...`, ~L65, L220) | PASS |
| **CRITICAL**: container path stays `/mnt/<root>/...` when host base is NOT `/mnt` | `tests/manifest/test_projection.py::TestBuildMountPlanningView::test_container_path_stays_fixed_at_mnt_when_host_base_differs` (host base `/custom/state/odoo-forge`; asserts `source_path` uses host root, `container_path == Path("/mnt/community/core/odoo")`) | **PASS** — independently verified `plan_backend.py:86` reads `evidence.container_path.parts[2]`, which stays `"community"` regardless of host base since `container_path` is built exclusively from the fixed `container_roots` (`MOUNT_ROOTS` default = `build_mount_roots(CONTAINER_MOUNT_BASE)`), never from the injected host `roots`. |
| Default host base still yields fixed container paths | Covered by the same guard test plus default-args regression tests in `test_projection.py` | PASS |
| `forge validate` scans/materializes/plans against resolved host roots | `tests/cli/test_validate.py::test_validate_scans_and_materializes_with_the_resolved_host_roots` (L219) | PASS |
| `forge project` checks out using resolved host roots | `tests/cli/test_project.py::test_project_checks_out_using_the_resolved_host_roots` (L102) | PASS |
| `forge unlock` resolves dest against resolved host `worktrees` root | `tests/cli/test_unlock.py::test_unlock_uses_the_resolved_host_roots` (L111) | PASS |
| `forge run` (backend) scans/materializes with resolved host roots | `tests/cli/test_backend.py::test_run_scans_and_materializes_with_the_resolved_host_roots` (L231) | PASS |
| Empty-string `FORGE_MOUNT_BASE` treated as unset | `tests/cli/test_mount_base.py::test_empty_string_forge_mount_base_is_treated_as_unset` | PASS (additional test beyond spec text, strengthens the "if base:" edge case documented in design.md) |

All 12 mapped scenarios have a real, passing, independently-executed covering test. No scenario is untested.

### Design Coherence
- `CONTAINER_MOUNT_BASE = Path("/mnt")` constant + `build_mount_roots(base)` helper implemented exactly as designed; `MOUNT_ROOTS = build_mount_roots(CONTAINER_MOUNT_BASE)` preserves old behavior.
- `plan_projection`/`plan_unlock` take `roots: Mapping[str, Path] = MOUNT_ROOTS` — matches design interface contract.
- `build_mount_planning_view` takes separate `roots` (host) and `container_roots: Mapping[str, Path] = MOUNT_ROOTS` (container) — matches the two-table design; `_match_root_and_layer`/`expected_path` on host, `MountEvidence.container_path` + dedup `container_paths` on container. Confirmed by direct code inspection.
- `_resolve_mount_base()` in `main.py` mirrors `_default_authority()` shape (`FORGE_MOUNT_BASE` → `XDG_STATE_HOME` → `~/.local/state`, all `.expanduser()`d) as specified.
- `_HOST_ROOTS` built once at module import time in `main.py`; `tests/conftest.py` pins `FORGE_MOUNT_BASE=/mnt` at collection time to keep the ~10 pre-existing `/mnt`-hardcoded CLI tests green — a deliberate, documented workaround for the import-time freeze, not a design deviation.
- No routing/shell/subprocess/provenance boundary touched — matches design's "Threat Matrix: N/A".

### Issues

**CRITICAL**: none.

**WARNING**:
1. `uv run ruff format --check .` reports `src/odoo_forge/manifest/projection.py` would be reformatted (2 long-line joins in the `container_path`/dedup construction added by this change). Not caught by task 3.x (which only ran pytest + lint-imports + grep). Cosmetic, does not affect behavior or type safety — recommend `uv run ruff format src/odoo_forge/manifest/projection.py` before archive.
2. Strict TDD is active for this session, but the retrieved `apply-progress` Engram observation (#8873) does not contain a literal per-task "TDD Cycle Evidence" table (RED/GREEN/TRIANGULATE/SAFETY NET columns) — it documents RED/GREEN narratively per phase and cites the final full-suite evidence instead. Substance is verifiable (all cited tests exist and pass, tasks.md itself marks explicit RED/GREEN sub-steps per task), so this is downgraded from the skill's default CRITICAL to WARNING — process-documentation gap only, not a build/behavior gap.

**SUGGESTION**: none.

### Backward Compatibility
- `FORGE_MOUNT_BASE=/mnt` reproduces prior hardcoded `/mnt/*` host behavior exactly, verified both by the dedicated unit test and by the fact that all ~10 pre-existing CLI test files (pinned via `tests/conftest.py`) stayed green with zero edits to their bodies.

**Next recommended**: archive (after optionally running `ruff format` on `projection.py`).
