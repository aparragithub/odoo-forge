## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 560-780 additions + deletions |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Delivery Boundaries

- Keep this change contract-only: no workflow/adaptor consumer wiring in this change.
- Deliver in three review-safe slices, each independently testable and rollback-safe.
- Use strict TDD in every slice: RED → GREEN → TRIANGULATE → REFACTOR.
- Keep tests with the behavior they verify; do not split tests away from code.

## 1. Slice 1 — Durable operation values and redacted failures

- [x] RED: Add failing tests in `tests/durable_operations/test_types.py` for immutable operation identity binding, replay-safe request digest comparison, lifecycle/value invariants, redacted evidence, and owned-only compensation scope.
- [x] GREEN: Implement `src/odoo_forge/durable_operations/types.py`, `src/odoo_forge/durable_operations/errors.py`, and `src/odoo_forge/durable_operations/__init__.py` with the immutable models and typed redacted failures described by the spec/design.
- [x] TRIANGULATE: Run `uv run pytest tests/durable_operations/test_types.py` and confirm the models serialize/validate without exposing secrets, connection material, or protected data bytes.
- [x] REFACTOR: Tighten field names, typing, and exports only; no behavioral drift.
- [x] Rollback boundary: remove the new durable-operations value-object and error modules plus `tests/durable_operations/test_types.py`; leave all existing workflows untouched.

## 2. Slice 2 — Pure transition service

- [x] RED: Add failing tests in `tests/durable_operations/test_service.py` for same-input replay, mismatched replay conflict, forward-only lifecycle progression, durable checkpoint resume, unknown-progress reconciliation, terminal bundle atomicity, residual cleanup visibility, and compensation ownership checks.
- [x] GREEN: Implement `src/odoo_forge/durable_operations/service.py` as a pure transition engine that produces recovery plans, terminal bundles, and monotonic revisions without selecting a store or scheduler.
- [x] TRIANGULATE: Run `uv run pytest tests/durable_operations/test_service.py` plus `uv run pytest tests/durable_operations/test_types.py` to confirm the service and types stay aligned.
- [x] REFACTOR: Consolidate transition helpers and keep provider reconciliation as an input, not a workflow decision leak.
- [x] Rollback boundary: remove `src/odoo_forge/durable_operations/service.py` and `tests/durable_operations/test_service.py`; retain the slice-1 value objects and errors.

## 3. Slice 3 — Persistence and recovery ports

- [x] RED: Add contract tests in `tests/ports/test_durable_operation_store.py` for create-or-load replay, conflict rejection, checkpoint append/replace semantics, compare-and-swap terminal commit, residual updates, and recoverable-operation queries.
- [x] GREEN: Implement `src/odoo_forge/ports/durable_operation_store.py` and `src/odoo_forge/ports/durable_operation_recovery.py` as provider-neutral ports, keeping them adapter-free and workflow-agnostic.
- [x] TRIANGULATE: Run `uv run pytest tests/ports/test_durable_operation_store.py`, then `uv run pytest`, `uv run lint-imports`, `uv run mypy`, and `uv run ruff check` to confirm the ports do not break architecture or typing boundaries.
- [x] REFACTOR: Normalize method names and docstrings only; do not introduce persistence implementation details.
- [x] Rollback boundary: remove the new port modules and `tests/ports/test_durable_operation_store.py`; no adapter wiring should exist yet.

## 4. Final cross-slice validation

- [x] Confirm all durable-operations tests pass together and that no consumer workflow imports the new capability prematurely.
- [x] Verify the diff stays inside the planned chain slices and still fits the review budget per PR.
- [x] Record any follow-up consumer adoption as a separate change after this contract lands.
