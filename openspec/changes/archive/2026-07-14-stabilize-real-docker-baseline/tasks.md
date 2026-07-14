# Tasks: Stabilize the Real-Docker Baseline

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated authored changed lines | 220–340 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes (forced) |
| Suggested split | One baseline child |
| Delivery strategy | interactive |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Repair the test-only harness defects, then prove the real-Docker baseline | Child #1; base = `feature/stabilize-real-docker-baseline` tracker | `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q`; `uv run pytest -q`; `uv run ruff check tests/adapters/test_docker_provider_integration.py`; `uv run mypy tests/adapters/test_docker_provider_integration.py`; `uv run lint-imports` | `ODOO_FORGE_TEST_ODOO_IMAGE=... uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q`; acceptance stays incomplete until this passes | Revert only `tests/adapters/test_docker_provider_integration.py`; no product/factory changes |

Tracker: draft/no-merge `feature/stabilize-real-docker-baseline`; child #1 targets tracker. Do not create branches or PRs here.

## Phase 1: Characterization and Fixture Foundation

- [x] 1.1 Characterize the skip/provider contract; preserve integration marking and default-suite exclusion.
- [x] 1.2 RED/GREEN: missing Docker skips; invalid image selection and post-detection failures fail.
- [x] 1.3 RED/GREEN: require factory labels/version and pinned `postgres:16`; reject unsafe selection.
- [x] 1.4 Create UUID ownership, ephemeral ports, `tmp_path`, and in-memory injector credentials.

## Phase 2: Lifecycle RED-to-GREEN Implementation

- [x] 2.1 RED/GREEN: prove secrets stay out of argv, logs, diagnostics, fixtures, and evidence; retain unconditional cleanup.
- [x] 2.2 RED/GREEN: prove PostgreSQL/Odoo readiness and ephemeral ports through provider `run`.
- [x] 2.3 RED/GREEN: prove live `status` and the `run -> status -> stop` lifecycle.
- [x] 2.4 RED/GREEN: prove `stop` removes containers/network and preserves both lifecycle volumes.

## Phase 3: Ownership Cleanup and Verification

- [x] 3.1 RED/GREEN: cleanup success, partial setup, and failure deletes only owned resources with accumulated errors.
- [x] 3.2 RED/GREEN: residual queries distinguish preserved volumes from owned leaks.
- [x] 3.3 Run default suite and explicit integration command; run static checks and record Docker client/server versions, image labels, readiness, status, preservation, cleanup, and residual results.
- [x] 3.4 Applied the defect-extraction stop rule; production and assertions were unchanged.

## Phase 4: Harness Defect RED-to-GREEN Repairs

- [x] 4.1 RED: absent network/container/volume cleanup is idempotent, but real failures remain errors; GREEN `_cleanup`.
- [x] 4.2 RED: label extraction avoids `BaseModel.labels`; GREEN with a typed inspect metadata boundary.
- [x] 4.3 RED: expose Ruff E501 in the factory-label assertion; GREEN by formatting only the harness.
- [x] 4.4 RED: factory labels validate before immutable digest resolution; GREEN locks `repo@sha256:...` before provider pull.

## Phase 5: Verification and Acceptance

- [x] 5.1 Run focused tests after each RED/GREEN pair; retain integration marking, secret safety, ownership scope, and default exclusion.
- [x] 5.2 Run `uv run pytest -q`, `uv run ruff check tests/adapters/test_docker_provider_integration.py`, `uv run mypy tests/adapters/test_docker_provider_integration.py`, and `uv run lint-imports`.
- [x] 5.3 Run the table's exact Docker command, record receipt/residuals, and mark acceptance only after `run -> status -> stop` passes.
