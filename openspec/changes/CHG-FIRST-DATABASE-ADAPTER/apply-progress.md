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
