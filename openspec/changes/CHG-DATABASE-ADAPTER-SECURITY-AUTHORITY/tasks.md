# Tasks: Docker Database Adapter Security Authority

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | PR 3A: 348 existing; PR 3B: 94 minimum; PR 4–5: 180–380 each |
| 400-line budget risk | High overall; each PR <=400 |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3A → PR 3B → PR 4 → PR 5 |
| Delivery strategy | force chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR / base | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 3A | Preserve and verify correction-backed authority/default/provision/ID/fail-closed behavior | PR 3A → PR 2 | `uv run pytest tests/adapters/test_postgres_docker_authority.py tests/adapters/test_postgres_docker_provider.py -q` | N/A: correction boundary is mocked/unit Docker | Revert only current 348-line authority/provider correction and tests |
| 3B | Add remaining durable lifecycle transitions and unsupported-runtime rejection | PR 3B → PR 3A | targeted provider lifecycle tests | N/A: mocked Docker; real runtime is PR 5 | Revert only reserve/bind/activate/retire code and tests |
| 4 | Credential-safe `_FILE` injection | PR 4 → PR 3B | secret-injection tests | N/A: protected file boundary | Revert injection module/wiring/tests |
| 5 | Real-Docker readiness and final lineage proof | PR 5 → PR 4 | full focused Docker/readiness suite | Docker >=24 with `postgres:16` | Revert readiness/integration/evidence only |

## Phase 1: Custody Foundation

- [x] 1.1–1.2 Complete `authority.py` custody and failure-closed persistence with tests.

## Phase 2: Signing and Evidence

- [x] 2.1–2.3 Complete signed records, key recovery/rotation, evidence APIs, dependency, and verification.

## Phase 3A: Existing Correction Boundary (PR 3A)

- [x] 3A.1 Preserve correction-backed default authority, provision persistence, signed immutable Docker-ID verification, and label-only fail-closed rejection; evidence is 348 authored lines and the reverted +94-line attempt remains excluded.
- [x] 3A.2 RED/GREEN/verify the bounded provider/authority regression suite; target `feature/tracker` from PR 3A and keep `review-093c1c067f361178` untouched.

## Phase 3B: Remaining Lifecycle (PR 3B)

- [x] 3B.1 RED: add tests for reserve-before-Docker, bind/activate/retire transitions, missing/lost authority, pre-advance failures, shell/injected IDs, and unsupported runtime; expect fail-closed typed errors.
- [x] 3B.2 GREEN: implement the smallest `authority.py`/`provider.py` lifecycle transition set and verified-ID mutation/reconcile/rollback/cleanup wiring; PR 3B targets PR 3A and stays <=400 lines.
- [x] 3B.3 Verify focused pytest, Ruff, and mypy; record rollback as reverting only PR 3B lifecycle code/tests.

## Phase 4: Safe Injection (PR 4)

- [x] 4.1 RED/GREEN: create `secret_injection.py`, wire protected bind files and PostgreSQL `_FILE`, erase after readiness, and prove no plaintext/fallback; target PR 3B.

## Phase 5: Integration and Final Proof (PR 5)

- [x] 5.1 RED/GREEN: verify restart cleanup, foreign survival, forged/stale/missing evidence, secret absence, and final signed lineage with Docker/readiness tests; target PR 4.
- [x] 5.2 Run pytest, build, import-linter, mypy, Ruff, and final-lineage archive verification; never touch the prohibited review.
