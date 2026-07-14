# Apply Progress: Stabilize the Real-Docker Baseline

**Status:** Complete — the test-only child passes its real-Docker receipt and default suite. Historical blocked rows below remain append-only snapshots, not current dependency state.

## Delivery Boundary

- Strategy: forced Feature Branch Chain.
- Work unit: Child #1, test-only lifecycle evidence.
- Intended boundary: replace only `tests/adapters/test_docker_provider_integration.py` and test-owned helpers; no production files changed.
- Review impact: 286 authored lines (266 additions, 20 deletions) in the test file; below the 400-line budget.
- Rollback boundary: revert only `tests/adapters/test_docker_provider_integration.py`. No production behavior or user-owned Docker resource was changed.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | `1 skipped` baseline | Replaced skipped skeleton | Blocked by runtime defect | Pending | Not reached |
| 1.2 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Prerequisite-skip path written | Not reached | Pending | Not reached |
| 1.3 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | `env -u ODOO_FORGE_TEST_ODOO_IMAGE ...` failed as expected | Blocked by runtime defect | Factory labels verified | Not reached |
| 1.4 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Unique plan, labels, ports, `tmp_path`, and in-memory injector written | Blocked by runtime defect | Pending | Not reached |
| 2.1 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Generated secret and exception redaction assertion written | Blocked by runtime defect | Pending | Not reached |
| 2.2 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Direct `run` readiness assertion written | Failed: Odoo never became healthy | Pending | Not reached |
| 2.3 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | `status` assertions written | Not reached | Not reached | Not reached |
| 2.4 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | `stop` preservation assertions written | Not reached | Not reached | Not reached |
| 3.1 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Unconditional exact-name cleanup written | Runtime cleanup attempted | Pending | Not reached |
| 3.2 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Independent label residual queries written | Runtime residual queries passed | Pending | Not reached |
| 3.3 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Same baseline | Explicit integration command executed | Failed at readiness; remaining checks intentionally not run | Pending | Not reached |
| 3.4 | N/A | Real Docker integration | N/A | Stop-rule condition observed | Applied: no production change or weakened assertion | N/A | N/A |

## Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command | Baseline: `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` → `1 skipped in 0.02s`. RED: `env -u ODOO_FORGE_TEST_ODOO_IMAGE uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` → `1 failed in 0.32s`, required image selector absent. Runtime: `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` → `1 failed in 219.53s`; Odoo health did not become healthy within 180 seconds. |
| Runtime harness | Docker client/server `29.6.1/29.6.1`. Built with `./factory/build.sh 19.0` → `ghcr.io/aparragithub/odoo-ce:19`; image id `sha256:7403c677e133bd4dedf1ba600332deec2e45569d90db010def06853662ed1399`, source label `https://github.com/aparragithub/odoo-forge`, version `19.0`, revision `65dbcabcd243abf24d6d3c3788d2caff66485790`. PostgreSQL remained `postgres:16`, id `sha256:eb4759788a2182f08257135e61a34f2cfc3c2914079f3465d64ee62350f4d081`. |
| Failure and cleanup receipt | PostgreSQL reached readiness; Odoo reported `Waiting for PostgreSQL` then `PostgreSQL is ready!`, but provider readiness timed out after 180 seconds. Provider rollback ran. Independent exact label checks for containers, networks, and volumes for the generated test identity returned no residuals. Evidence contains no generated secret. |
| Rollback boundary | Revert only `tests/adapters/test_docker_provider_integration.py`; it is test-only and deletes resources only by its generated ownership labels and exact names. |

## Reconciled TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 3.3 | `tests/adapters/test_docker_provider_integration.py` | Integration | Previous real-Docker run failed only during final cleanup | Prior receipt retained below | `uv run pytest -q` → 541 passed, 4 deselected | Explicit runtime run now passes | No production refactor |
| 4.1 | `tests/adapters/test_docker_provider_integration.py` | Unit helper | Existing runtime test: failed cleanup on already-absent network | `-k 'cleanup or factory_image_resolves'` → 2 failed, 1 passed; absent resources were errors | Same command → 3 passed, 1 deselected | Absent container/network/volume and permission-denied errors | Narrow lowercase absent-message check |
| 4.2 | `tests/adapters/test_docker_provider_integration.py` | Static typing | Focused helper tests passed | `uv run mypy` → `BaseModel` incompatible with typed resource labels | `uv run mypy` → Success: no issues in 105 source files | Network, volume, and container resources share typed label extraction | Typed resource tuple only |
| 4.3 | `tests/adapters/test_docker_provider_integration.py` | Static lint | Focused helper tests passed | `uv run ruff check ...` → E501 at factory revision assertion | `uv run ruff check ...` → All checks passed | Formatter check → 1 file already formatted | Formatting only |
| 4.4 | `tests/adapters/test_docker_provider_integration.py` | Unit helper + real Docker | Existing runtime cleanup failure recorded below | `_factory_image` test returned mutable `:19` instead of expected digest | Focused command → 3 passed, 1 deselected | Real command selected `:19`, validated labels, and provider used immutable digest | Extracted metadata/label/digest helpers |
| 5.1 | `tests/adapters/test_docker_provider_integration.py` | Integration | All focused tests after repairs | N/A — verification task | Focused 3 passed; runtime 4 passed | Explicit daemon path preserved | None needed |
| 5.2 | `tests/adapters/test_docker_provider_integration.py` | Regression/static | N/A — verification task | N/A | pytest, mypy, Ruff, format, and import boundaries passed | Default suite excludes 4 integration tests | None needed |
| 5.3 | `tests/adapters/test_docker_provider_integration.py` | Real Docker integration | Previous failing receipt retained | N/A — acceptance task | Explicit Docker command → 4 passed in 27.03s | Internal exact-name/label residual checks passed | None needed |

## Current Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused helper command | `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q -k 'cleanup or factory_image_resolves'` → `3 passed, 1 deselected in 0.28s`. |
| Static commands | `uv run mypy` → Success: no issues in 105 source files; `uv run ruff check tests/adapters/test_docker_provider_integration.py` → All checks passed; `uv run ruff format --check tests/adapters/test_docker_provider_integration.py` → 1 file already formatted; `uv run lint-imports` → 6 contracts kept, 0 broken. |
| Default suite | `uv run pytest -q` → `541 passed, 4 deselected in 3.63s`; the integration marker remains excluded by default. |
| Runtime harness | `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` → `4 passed in 27.03s`. It completed `run -> status -> stop`, observed ephemeral Odoo ports, preserved named volumes after `stop`, final-cleaned exact owned resources, and passed independent exact label/name residual checks. |
| Docker/image receipt | Docker client/server `29.6.1/29.6.1`. Selected tag `ghcr.io/aparragithub/odoo-ce:19` validated source `https://github.com/aparragithub/odoo-forge`, version `19.0`, revision `65dbcabcd243abf24d6d3c3788d2caff66485790`, then resolved before planning/pull to `ghcr.io/aparragithub/odoo-ce@sha256:7403c677e133bd4dedf1ba600332deec2e45569d90db010def06853662ed1399`. PostgreSQL stayed `postgres:16`. |
| Secret and cleanup safety | Generated credentials remained in memory and no secret appeared in the recorded command/results. The harness accepts only already-absent owned resources during final cleanup; permission and other real cleanup failures remain reported. |
| Rollback boundary | Revert only `tests/adapters/test_docker_provider_integration.py`; no provider, factory, readiness-fix, or production artifact changes are part of this child. |

## Preserved Previous Failing Receipt

The original readiness/cleanup receipt in the preceding **Work Unit Evidence** table is retained unchanged for auditability. It records the earlier 180-second readiness failure and the later already-absent-network cleanup failure; neither was erased or treated as a production change in this test-only child.

## Latest Accepted Verification Reconciliation

This current evidence supplements, and does not replace, the four-test runtime receipt above or any earlier failure receipt.

| Evidence | Exact accepted result |
|---|---|
| Provider focused suite | `uv run pytest tests/adapters/test_docker_provider.py -q` → `90 passed in 2.46s`. |
| Default suite | `uv run pytest` → `545 passed, 6 deselected in 3.72s`; configured aggregate coverage 98%. |
| Real-Docker acceptance | `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` → `6 passed in 27.59s`; `run -> status -> stop` and independent residual queries passed. |
| Accepted verification totals | `openspec/changes/archive/2026-07-14-fix-odoo-factory-health-readiness/verify-report.md` records PASS: 3/3 requirements, 8/8 scenarios, 16/16 tasks, 0 blockers, and 0 critical findings. |

## Remaining Work

None. All baseline tasks are marked complete. Ready for `sdd-verify`.
