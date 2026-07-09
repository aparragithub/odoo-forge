# Tasks: SP1-B — Runtime Digest Consumption for Local Docker

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 260-380 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | force-chained |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Thread runtime digest input into planning | PR 1 | Base: main; add CLI/planner tests for override vs fallback. |
| 2 | Pull planned image in local Docker run | PR 2 | Base: PR 1; keep pull logic and typed error mapping in Docker adapter. |
| 3 | Verify CLI pull diagnostics end-to-end | PR 3 | Base: PR 2; confirm single-line operator errors and no traceback. |

## Phase 1: Foundation / Planning seam

- [x] 1.1 Update `src/odoo_forge/backend/plan.py` so `plan_backend(..., odoo_image=None)` remains the single source for `BackendPlan.odoo.image` selection.
- [x] 1.2 Add `--odoo-image-ref` parsing/validation in `src/odoo_forge_cli/main.py` using the existing digest helper, and pass the normalized ref into planning.

## Phase 2: Docker runtime behavior

- [x] 2.1 Modify `src/odoo_forge_docker/provider.py` to run `docker pull` for `plan.odoo.image` before `docker run`.
- [x] 2.2 Classify pull failures into typed backend errors in `src/odoo_forge/backend/errors.py` and the Docker adapter, covering daemon unavailable, image not found, and auth/access denied.
- [x] 2.3 Keep non-Docker backends and non-run actions unchanged; no pull contract leaks outside the Docker adapter.

## Phase 3: Testing / Verification

- [x] 3.1 Extend `tests/backend/test_plan.py` for override-vs-template image selection and the no-override fallback.
- [x] 3.2 Extend `tests/adapters/test_docker_provider.py` for pull-before-run ordering and typed pull failure mapping.
- [x] 3.3 Extend `tests/cli/test_backend.py` for `forge run --odoo-image-ref` success, malformed-ref fail-fast, and single-line `error: ...` output.

## Phase 4: Cleanup / Documentation

Slice 3 ownership is hygiene only: keep comments/docs aligned with the already-implemented runtime behavior, and do not add new CLI/backend behavior here.

- [x] 4.1 Align docstrings/comments in `src/odoo_forge_cli/main.py`, `src/odoo_forge/backend/plan.py`, and `src/odoo_forge_docker/provider.py` with the ephemeral override and pull ownership boundaries.
- [x] 4.2 Remove any temporary test scaffolding after the TDD loop and confirm no `project.lock` or registry-resolution files were touched.
