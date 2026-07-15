# Tasks: Database Adapter Verification Closure

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 90–150 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | One forced-chained child after parent PR4 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Close residual reporting and readiness policy on the integrated parent baseline | Next child after PR4; target integrated/rebased PR4 branch | `uv run pytest tests/adapters/test_postgres_docker_provider.py tests/database/test_readiness.py` | N/A: pure closure; parent PR4 real-Docker evidence remains a prerequisite | Revert the four listed source/test files only |

## Phase 1: Parent Integration and RED Tests

- [x] 1.1 Confirm parent PR4 is integrated, rebase this child onto the integrated PR4 branch, and verify the child diff contains only this closure.
- [x] 1.2 RED: in `tests/adapters/test_postgres_docker_provider.py`, make persistent credential unlink failure with successful container rollback expect `RollbackIncompleteError`, receipt, empty `residual_failures`, opaque `("credential-file",)`, chained cause, exact rollback, and no path/secret/handle/descriptor.
- [x] 1.3 RED: in `tests/database/test_readiness.py`, parameterize each runtime-proof flag as `None` and `False` with otherwise complete evidence; assert not-ready and the exact blocking flag.

## Phase 2: Minimal GREEN Implementation

- [x] 2.1 GREEN: modify `src/odoo_forge_postgres_docker/provider.py` so `_raise_after_rollback` raises existing `RollbackIncompleteError` when resource or cleanup residuals remain, preserving receipt, cause, tuples, and redaction.
- [x] 2.2 GREEN: modify `src/odoo_forge/database/readiness.py` with nullable `real_docker_verified` and `ownership_safety_verified`; require literal `True` for readiness and report unsatisfied flag names.

## Phase 3: Verification and Boundary Checks

- [x] 3.1 Run focused adapter/readiness tests, then default suite: `uv run pytest`.
- [x] 3.2 Run static checks: `uv run ruff check`, `uv run mypy`, and `uv run lint-imports`.
- [x] 3.3 Run build verification: `uv build`; record parent PR4 runtime evidence as the prerequisite and no new real-Docker harness for this pure policy closure.
- [x] 3.4 Confirm exclusions: no provider-neutral API, portfolio/control-plane, routing, migration, runtime cutover, or parent-artifact changes; document rollback as reverting this child unit.
