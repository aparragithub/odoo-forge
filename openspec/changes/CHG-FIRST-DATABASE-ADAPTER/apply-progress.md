# Apply Progress: First Docker PostgreSQL Database Adapter

## Work Units

- Delivery mode: `auto-chain`, feature-branch-chain.
- PR 1 boundary: `feat/chg-first-database-adapter-01-foundation` targets
  `feat/chg-first-database-adapter` and contains only Docker command and ownership-proof
  foundation.
- PR 2 boundary: `feat/chg-first-database-adapter-02-lifecycle` targets
  `feat/chg-first-database-adapter-01-foundation` and contains only lifecycle behavior.
- Completed tasks: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/adapters/test_postgres_docker_provider.py` | Unit | N/A (new files) | ✅ Initial run: collection failed with `ModuleNotFoundError` | ✅ 5 passed | ✅ hostile and safe identifiers; timeout and nonzero failures | ✅ failure details remain redacted |
| 1.2 | `tests/adapters/test_postgres_docker_provider.py` | Unit | N/A (new files) | ✅ Tests referenced missing adapter module | ✅ 5 passed | ✅ argv execution and ownership proof cases | ✅ constants and isolated runner extracted |
| 1.3 | `tests/adapters/test_postgres_docker_provider.py` | Unit | N/A (new source file) | ✅ Type-contract test failed because `credentials` was `object` | ✅ 9 passed | ✅ protocol, concrete type hints, and source import isolation | ✅ provider annotations match the port; no behavior change |
| 2.1 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 9 passed | ✅ focused RED command: 5 failed (`NotImplementedError`/missing lifecycle constructor dependencies) | ✅ 6 lifecycle tests passed | ✅ created-only provision, bounded readiness, reverse rollback, reconcile, foreign survival, and zero residuals | ✅ shared owned-label fixture removes duplication |
| 2.2 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 9 passed | ✅ lifecycle tests existed before production changes; `adopt` RED failed with `NotImplementedError` | ✅ 6 lifecycle tests passed, then `adopt` test passed | ✅ provision success/failure, cleanup success/foreign-residual paths, and no-mutation adoption | ✅ lifecycle remains isolated; no DPROV-DB wiring or runtime cutover added |
| 2.3 | `tests/adapters/test_postgres_docker_provider.py` | Unit | ✅ 15 passed | ✅ receipt-membership delete test failed with typed command failure, exposing inspection before membership proof | ✅ 7 destructive-path tests passed | ✅ receipt mismatch, forged labels, and foreign labels follow distinct refusal paths | ✅ extracted `_remove_owned`; membership is checked before live inspection and then live labels are proved |

## Test Summary

- Total tests written: 22.
- Total tests passing: 22.
- Layers used: Unit (22).
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

## Deviations and Issues

None — implementation matches the PR 1 and PR 2 design boundaries. `restore` intentionally remains unimplemented for the later handoff slice; no CAP handoff, package registration, local-backend extraction, or runtime cutover was added.

## Correction Evidence

- Review `review-d41fd1bf14d7e752`: Docker inspect labels now parse from the first array object at `.Config.Labels`.
- TDD: focused lifecycle test RED with the prior flat-label parser; GREEN after the parser correction.
