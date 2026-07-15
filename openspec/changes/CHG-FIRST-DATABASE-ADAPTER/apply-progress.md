# Apply Progress: First Docker PostgreSQL Database Adapter

## Work Units

- Delivery mode: `auto-chain`, feature-branch-chain.
- PR 1 boundary: `feat/chg-first-database-adapter-01-foundation` targets
  `feat/chg-first-database-adapter` and contains only Docker command and ownership-proof
  foundation.
- PR 2 boundary: `feat/chg-first-database-adapter-02-lifecycle` targets
  `feat/chg-first-database-adapter-01-foundation` and contains only lifecycle behavior.
- PR 3 boundary: `feat/chg-first-database-adapter-03-handoffs` targets
  `feat/chg-first-database-adapter-02-lifecycle` at `4628d77f13a70229b3f2c4196f4d2bcf6638ba89`
  and contains only CAP credential/artifact handoffs and restore validation.
- Completed tasks: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/adapters/test_postgres_docker_provider.py` | Unit | N/A (new files) | ✅ Initial run: collection failed with `ModuleNotFoundError` | ✅ 5 passed | ✅ hostile and safe identifiers; timeout and nonzero failures | ✅ failure details remain redacted |
| 1.2 | `tests/adapters/test_postgres_docker_provider.py` | Unit | N/A (new files) | ✅ Tests referenced missing adapter module | ✅ 5 passed | ✅ argv execution and ownership proof cases | ✅ constants and isolated runner extracted |
| 1.3 | `tests/adapters/test_postgres_docker_provider.py` | Unit | N/A (new source file) | ✅ Type-contract test failed because `credentials` was `object` | ✅ 9 passed | ✅ protocol, concrete type hints, and source import isolation | ✅ provider annotations match the port; no behavior change |
| 2.1 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 9 passed | ✅ focused RED command: 5 failed (`NotImplementedError`/missing lifecycle constructor dependencies) | ✅ 6 lifecycle tests passed | ✅ created-only provision, bounded readiness, reverse rollback, reconcile, foreign survival, and zero residuals | ✅ shared owned-label fixture removes duplication |
| 2.2 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 9 passed | ✅ lifecycle tests existed before production changes; `adopt` RED failed with `NotImplementedError` | ✅ 6 lifecycle tests passed, then `adopt` test passed | ✅ provision success/failure, cleanup success/foreign-residual paths, and no-mutation adoption | ✅ lifecycle remains isolated; no DPROV-DB wiring or runtime cutover added |
| 2.3 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 15 passed | ✅ receipt-membership delete test failed with typed command failure, exposing inspection before membership proof | ✅ 7 destructive-path tests passed | ✅ receipt mismatch, forged labels, and foreign labels follow distinct refusal paths | ✅ extracted `_remove_owned`; membership is checked before live inspection and then live labels are proved |
| 3.1 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 22 passed | ✅ focused collection failed: missing `target_handoffs` module | ✅ 5 focused handoff/redaction tests passed | ✅ opaque credential descriptor, database component reference, and pre-mutation validation failure | ✅ tests use a typed in-memory artifact capability and Docker runner double |
| 3.2 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 22 passed | ✅ tests referenced missing handoff functions/module | ✅ 5 focused handoff/redaction tests passed | ✅ direct target handoffs and provider restore wiring use distinct inputs | ✅ isolated target handoff module; provider-neutral contracts unchanged |
| 3.3 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 27 passed | ✅ parameterized failure cases were written before typed failure mapping | ✅ 5 focused handoff/redaction tests passed | ✅ unavailable, coherence, and integrity failure codes map to distinct typed redacted errors | ✅ shared failure mapper avoids repeated redaction branches |

## Test Summary

- Total tests written: 28.
- Total tests passing: 28.
- Layers used: Unit (28).
- Approval tests: None — new adapter foundation.
- Pure functions created: 2 (`_run_subprocess`, `_creator_token`); lifecycle dependencies are injected for deterministic unit tests.

## Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_postgres_docker_provider.py` — exit 0; 9 passed. |
| Architecture/type/lint checks | `uv run mypy` — exit 0, no issues in 108 source files; `uv run lint-imports` — exit 0, 6 contracts kept; `uv run ruff check src/odoo_forge_postgres_docker tests/adapters/test_postgres_docker_provider.py` — exit 0, all checks passed. |
| Runtime harness command/scenario and exact result | N/A — this PR is a mocked subprocess safety foundation; provisioning and real-Docker lifecycle evidence are deliberately deferred to PR 4. |
| Rollback boundary | Remove `src/odoo_forge_postgres_docker/` and `tests/adapters/test_postgres_docker_provider.py`; this removes only the unselected foundation and does not affect local-backend routing or provider-neutral contracts. |

## Work Unit Evidence: PR 2 Lifecycle

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_postgres_docker_provider.py -k 'provision or reconcile or cleanup or rollback'` — exit 0; 6 passed, 10 deselected. |
| Focused file command and exact result | `uv run pytest tests/adapters/test_postgres_docker_provider.py` — exit 0; 17 passed. |
| Architecture/type/lint checks | `uv run mypy` — exit 0, no issues in 108 source files; `uv run lint-imports` — exit 0, 6 contracts kept; `uv run ruff check src/odoo_forge_postgres_docker tests/adapters/test_postgres_docker_provider.py` — exit 0, all checks passed. |
| Runtime harness command/scenario and exact result | `docker version` — client version 29.6.1 returned, then daemon access failed: `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`. Full real lifecycle evidence remains deliberately deferred to PR 4. |
| Rollback boundary | Revert only PR 2 changes in `src/odoo_forge_postgres_docker/provider.py` and `tests/adapters/test_postgres_docker_provider.py`; this removes provision/reconcile/delete/cleanup behavior without altering PR 1 runner/proof APIs, provider-neutral contracts, or runtime routing. |

## Work Unit Evidence: PR 3 Handoffs and Restore

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_postgres_docker_provider.py -k 'restore or redaction'` — exit 0; 5 passed, 23 deselected. |
| Focused file command and exact result | `uv run pytest tests/adapters/test_postgres_docker_provider.py` — exit 0; 28 passed. |
| Architecture/type/lint checks | `uv run mypy` — exit 0, no issues in 109 source files; `uv run lint-imports` — exit 0, 6 contracts kept; `uv run ruff check src/odoo_forge_postgres_docker tests/adapters/test_postgres_docker_provider.py` — exit 0, all checks passed. |
| Runtime harness command/scenario and exact result | N/A — target-side credential and artifact injectors are exercised with typed test doubles; real Docker restore evidence is deliberately deferred to PR 4. |
| Rollback boundary | Revert `src/odoo_forge_postgres_docker/target_handoffs.py` plus the PR 3 handoff changes in `provider.py` and tests; this removes CAP handoffs/restore validation only, retaining PR 1–2 ownership/lifecycle behavior and all provider-neutral contracts. |

## Deviations and Issues

None — implementation matches the PR 1–3 design boundaries. No package registration, local-backend extraction, runtime cutover, WF-DATA-COPY, control-plane authority, data-environments, or PublishedLayer/Override work was added.

## Correction Evidence

- Review `review-d41fd1bf14d7e752`: Docker inspect labels now parse from the first array object at `.Config.Labels`.
- TDD: focused lifecycle test RED with the prior flat-label parser; GREEN after the parser correction.
- Review `review-b21ef94145ece33e`: credential and restore target injector `RuntimeError` diagnostics now translate to typed, redacted database-provider failures.
- TDD: focused injector tests RED with raw exceptions; GREEN with `CredentialUnavailableError` and `DatabaseOperationError`, neither exposing supplied credential or artifact text.

## Work Unit Evidence: PR 4 Real-Docker Acceptance (Partial)

- PR 4 boundary: `feat/chg-first-database-adapter-04-real-docker` targets
  `feat/chg-first-database-adapter-03-handoffs` at
  `c7501726b08a0aef9cf3e43d5b8505841eef1dce`. It contains only opt-in
  real-Docker acceptance preparation and DPROV-DB evidence.
- Completed tasks remain: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3.
- Tasks 4.1, 4.2, and 4.3 remain incomplete; no checkbox was marked complete.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 4.1 | `tests/adapters/test_postgres_docker_provider_integration.py` | Integration | ✅ `uv run pytest tests/adapters/test_postgres_docker_provider.py` — exit 0; 30 passed | ⛔ Test harness written first; command skipped because the Docker daemon is unreachable | ⛔ Blocked — no real lifecycle ran | ⛔ Blocked — restore and forced rollback cases require daemon access | ⛔ Deferred until a real lifecycle can be green |
| 4.2 | `pyproject.toml`, integration test | Integration | N/A — no existing files modified | ⛔ Blocked before marker/package GREEN; registering the marker would not create real lifecycle evidence | ⛔ Blocked | ⛔ Blocked | ⛔ Deferred |
| 4.3 | `docs/specs/platform/portfolio.json` | Boundary | N/A — no existing files modified | ⛔ Blocked — no acceptance evidence exists to record | ⛔ Blocked | ⛔ Blocked | ⛔ Deferred |

### Partial Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_postgres_docker_provider_integration.py -m real_docker` — exit 0; 1 skipped, 1 `PytestUnknownMarkWarning`. The harness called `docker info` and skipped before provisioning because the daemon is unreachable. |
| Runtime harness command/scenario and exact result | `docker version` — client: Version `29.6.1`, API `1.55`, Go `go1.26.4-X:nodwarf5`, Git commit `8900f1d330`, OS/Arch `linux/amd64`, Context `default`; daemon result: `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`. No real Docker lifecycle executed. |
| Focused static check | `uv run ruff check tests/adapters/test_postgres_docker_provider_integration.py && uv run ruff format --check tests/adapters/test_postgres_docker_provider_integration.py` — exit 0; `All checks passed!`; `1 file already formatted`. |
| Rollback boundary | Remove only `tests/adapters/test_postgres_docker_provider_integration.py`; this removes the unexecuted opt-in harness and changes no production behavior, local-backend routing, or provider-neutral contract. |

### Blocker

The current user must grant this workspace access to the Docker daemon at
`/var/run/docker.sock` (or run the same branch in an environment where `docker info`
succeeds) without changing socket permissions, using `sudo`, or changing Docker service
configuration. Until then, the required provisioning/readiness, interrupted reconcile,
partial rollback, restore, redaction, foreign-survival, and complete-cleanup evidence
cannot be produced. No package marker, portfolio evidence, or task completion is valid
without that real lifecycle evidence.

## Work Unit Evidence: PR 4 Resume

- Docker daemon access was restored in the same workspace/process. PR 4 now has
  real-Docker evidence for tasks 4.1–4.2; task 4.3 remains incomplete only because
  the repository-wide Ruff format check fails on a pre-existing PR 3 file outside
  this work unit.
- Completed tasks: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1, 4.2.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 4.1 | `tests/adapters/test_postgres_docker_provider_integration.py` | Integration | ✅ 30 provider-unit tests passed | ✅ Real Docker initially failed bounded readiness because PostgreSQL lacked an initialization authentication setting; reconcile then exposed ID/name drift | ✅ 4 real-Docker tests passed | ✅ provision/readiness/reconcile/foreign cleanup; forced readiness rollback; restore handoff; credential and restore redaction | ✅ separate reconciler instance, typed artifact double, and unconditional cleanup paths remain focused |
| 4.2 | `pyproject.toml`, integration test | Integration | ✅ Initial 4-test harness passed but emitted unknown-marker warning | ✅ `real_docker` warning exposed missing marker registration | ✅ 4 real-Docker tests passed without warning after package/root/marker registration | ➖ Structural configuration only | ✅ focused configuration additions only |
| 4.3 | `docs/specs/platform/portfolio.json` | Boundary | ✅ Default pytest: 577 passed, 10 deselected | ✅ Global `uv run ruff format --check` failed on unchanged `tests/adapters/test_postgres_docker_provider.py` | ⛔ Blocked by pre-existing format failure | ⛔ Blocked | ⛔ Do not alter the unrelated PR 3 file in this PR 4 slice |

### Real-Docker Evidence

| Evidence | Result |
|---|---|
| Focused lifecycle command | `uv run pytest tests/adapters/test_postgres_docker_provider_integration.py -m real_docker` — exit 0; 4 passed in 4.95s. |
| Lifecycle scenarios | A real `postgres:16` container reached `pg_isready`; a fresh provider reconciled its operation label; cleanup removed the owned container and left an independently created foreign container; forced readiness failure rolled back the real created container; restore passed only the opaque database component into the injector then cleaned up. |
| Redaction | Credential and restore injector failures used `integration-handoff-secret`; both surfaced typed errors without the secret. |
| Package/marker evidence | `real_docker` is registered and the focused command passed without `PytestUnknownMarkWarning`; Hatch and import-linter root package lists include `odoo_forge_postgres_docker`. |
| DPROV-DB portfolio evidence | `ADAPTER-DATABASE-DOCKER` and `CHG-FIRST-DATABASE-ADAPTER` record achieved DPROV-DB acceptance with evidence `S62`; no adjacent capability was changed. |
| Lint/type/test checks | `uv run lint-imports` — 6 kept, 0 broken; `uv run mypy` — no issues in 110 source files; `uv run ruff check` — all checks passed; `uv run pytest` — 577 passed, 10 deselected. |
| Format check blocker | `uv run ruff format --check` would reformat unchanged `tests/adapters/test_postgres_docker_provider.py`; `git diff c7501726b08a0aef9cf3e43d5b8505841eef1dce -- tests/adapters/test_postgres_docker_provider.py` is empty. |
| Rollback boundary | Revert PR 4 changes to `provider.py`, the integration test, `pyproject.toml`, the two DPROV-DB portfolio records, and this progress entry. This removes the adapter acceptance slice without changing local-backend routing, WF-DATA-COPY, control-plane authority, data environments, or PublishedLayer/Override. |

## Work Unit Evidence: PR 4 Final Format Resolution

- The maintainer explicitly accepted the inherited mechanical format correction in PR 4
  rather than rebuilding the PR3/PR4 chain.
- `uv run ruff format tests/adapters/test_postgres_docker_provider.py` reformatted only
  that test file; it changed no executable behavior.
- `uv run ruff format --check .` — exit 0; 113 files already formatted.
- `uv run pytest tests/adapters/test_postgres_docker_provider.py` — exit 0; 30 passed.
- `git diff --check` — exit 0.
- The accepted four-scenario real-Docker evidence remains valid because this follow-up
  changed only formatting; the real-Docker command was not rerun.
- All tasks are complete: 1.1–4.3 (12/12).

## Correction Evidence: Credential Authentication

- `review-cf4e54b633d8b277`: maintainer approved PR4 `size:exception`; native correction <150 lines.
- RED: both new tests raised `TypeError` for missing `credential_target`; GREEN: unit 31 passed,
  real Docker 5 passed. Missing/wrong TCP passwords failed; protected `PGPASSFILE` passed and cleanup removed the container.
- The adapter fails closed without a target and passes Docker only a protected `--env-file` path.
