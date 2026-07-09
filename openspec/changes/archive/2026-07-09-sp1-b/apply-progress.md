# Apply Progress: SP1-B — Runtime Digest Consumption for Local Docker

## Final Apply State

- All SP1-B slices are complete.
- Slice 1: CLI/planner seam for ephemeral runtime digest override.
- Slice 2: explicit local-Docker image pull plus typed pull-failure mapping.
- Slice 3: CLI pull-diagnostic verification and hygiene/doc alignment.
- No persisted lockfile or registry-resolution state was introduced.

## Completed Tasks

- [x] 1.1 Update `src/odoo_forge/backend/plan.py` so `plan_backend(..., odoo_image=None)` remains the single source for `BackendPlan.odoo.image` selection.
- [x] 1.2 Add `--odoo-image-ref` parsing/validation in `src/odoo_forge_cli/main.py` using the existing digest helper, and pass the normalized ref into planning.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/backend/test_plan.py` | Unit | ✅ 38/38 (`uv run pytest tests/backend/test_plan.py tests/cli/test_backend.py`) | ✅ Written | ✅ 41/41 | ✅ 2 cases | ✅ Clean |
| 1.2 | `tests/cli/test_backend.py` | Unit | ✅ 38/38 (`uv run pytest tests/backend/test_plan.py tests/cli/test_backend.py`) | ✅ Written | ✅ 41/41 | ✅ 2 cases | ✅ Clean |

## Commands Executed

- `uv run pytest tests/backend/test_plan.py tests/cli/test_backend.py` → 38 passed (safety net before implementation refinement)
- `uv run pytest tests/backend/test_plan.py tests/cli/test_backend.py` → 41 passed (green verification after implementation)

## Evidence Notes

- `tests/backend/test_plan.py` now covers explicit digest override precedence plus the existing fallback template behavior.
- `tests/cli/test_backend.py` now covers successful `--odoo-image-ref` propagation and malformed/non-digest fail-fast rejection with a single `error: ...` line.
- No slice-2 Docker runtime changes were applied.

## Slice 2

- Scope completed: explicit local-Docker `docker pull` before Odoo start + typed pull-failure mapping.
- Out of scope: CLI end-to-end diagnostics/testing remains for slice 3.

## Completed Tasks

- [x] 2.1 Modify `src/odoo_forge_docker/provider.py` to run `docker pull` for `plan.odoo.image` before `docker run`.
- [x] 2.2 Classify pull failures into typed backend errors in `src/odoo_forge/backend/errors.py` and the Docker adapter, covering daemon unavailable, image not found, and auth/access denied.
- [x] 2.3 Keep non-Docker backends and non-run actions unchanged; no pull contract leaks outside the Docker adapter.
- [x] 3.2 Extend `tests/adapters/test_docker_provider.py` for pull-before-run ordering and typed pull failure mapping.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 | `tests/adapters/test_docker_provider.py` | Integration | ✅ 42/42 (`uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py`) | ✅ Written | ✅ 46/46 | ✅ 2 cases | ✅ Clean |
| 2.2 | `tests/adapters/test_docker_provider.py` | Integration | ✅ 42/42 (`uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py`) | ✅ Written | ✅ 46/46 | ✅ 3 cases | ✅ Clean |
| 2.3 | `tests/adapters/test_docker_provider.py` + `tests/cli/test_backend.py` | Boundary invariant | ✅ 70/70 (`uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py tests/cli/test_backend.py`) | ✅ Written | ✅ 73/73 | ✅ `status`/`stop`/`logs`/`exec` keep pull local to `run()` | ✅ Clean |
| 3.2 | `tests/adapters/test_docker_provider.py` | Integration | ✅ 42/42 (`uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py`) | ✅ Written | ✅ 46/46 | ✅ 2 cases | ✅ Clean |

## Commands Executed

- `uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py` → 42 passed (safety net before implementation)
- `uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py` → 46 passed (green verification after implementation)
- `uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py tests/cli/test_backend.py` → 70 passed (regression check after slice 2)
- `uv run pytest tests/backend/test_errors.py tests/adapters/test_docker_provider.py tests/cli/test_backend.py` → 73 passed (regression check after adding the non-run no-pull negative test)

## Evidence Notes

- `DockerBackendProvider.run()` now performs an explicit `docker pull` for the planned Odoo image before any container start work.
- Pull failure mapping is typed at the Docker adapter boundary: daemon unavailable, image not found, and registry authorization/access denied each raise distinct backend errors.
- `status`/`stop`/`logs`/`exec` remain pull-free; the new negative test pins that `docker pull` stays local to `run()`.
- The CLI boundary still renders a single `error: ...` line and no traceback for backend failures.

## Slice 3

- Remaining ownership: CLI pull-diagnostic verification plus hygiene only (docstrings/comments + artifact alignment).
- Out of scope: any new CLI/backend behavior.

## Remaining Tasks

- [x] 4.1 Align docstrings/comments in `src/odoo_forge_cli/main.py`, `src/odoo_forge/backend/plan.py`, and `src/odoo_forge_docker/provider.py` with the ephemeral override and pull ownership boundaries.
- [x] 4.2 Remove any temporary test scaffolding after the TDD loop and confirm no `project.lock` or registry-resolution files were touched.

## Slice 3 Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 | `tests/backend/test_plan.py` | Unit | ✅ 38/38 (`uv run pytest tests/backend/test_plan.py tests/cli/test_backend.py`) | ✅ Written | ✅ 41/41 | ✅ 2 cases | ✅ Clean |
| 3.3 | `tests/cli/test_backend.py` | Boundary | ✅ 38/38 (`uv run pytest tests/backend/test_plan.py tests/cli/test_backend.py`) | ✅ Written | ✅ 41/41 | ✅ 3 cases | ✅ Clean |
| 4.1 | `src/odoo_forge_cli/main.py`, `src/odoo_forge/backend/plan.py`, `src/odoo_forge_docker/provider.py` | Hygiene | ✅ 90/90 (`uv run pytest tests/backend/test_plan.py tests/backend/test_errors.py tests/adapters/test_docker_provider.py tests/cli/test_backend.py`) | ➖ No new test needed | ✅ Doc/comment alignment verified | ✅ Matches spec/design boundaries | ✅ Clean |
| 4.2 | `openspec/changes/sp1-b/{tasks.md,apply-progress.md}` | Hygiene | ✅ 90/90 (`uv run pytest tests/backend/test_plan.py tests/backend/test_errors.py tests/adapters/test_docker_provider.py tests/cli/test_backend.py`) | ➖ No new test needed | ✅ No `project.lock` or registry-resolution writes | ✅ Drift reconciled with OpenSpec | ✅ Clean |
