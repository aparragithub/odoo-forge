# Apply Progress: CAP-DURABLE-OPERATIONS-RECORD-FIX

## Status: Complete (6/6 slices)

All slices implemented following strict TDD (RED -> GREEN -> REFACTOR). All tasks in
`tasks.md` are marked `[x]`.

## Slices

1. **Record invariant** (`src/odoo_forge/ports/durable_operation_store.py`) — added
   `_RESIDUAL_LIFECYCLES = frozenset({CLEANUP_REQUIRED, CLOSED})`; `__post_init__` residual
   branch now admits both states. `CLOSED` + non-empty residual retains `terminal_commit`.
   Empty-residual branch untouched. Regression test (`match="cleanup_required lifecycle"`)
   stays green verbatim.
2. **Port docstring** — `resolve_residual` docstring updated to state retention and the
   no-op-is-an-error rule (documentation only, no behavior change).
3. **Reference fake** (`tests/ports/test_durable_operation_store.py`) — `_ConformingDurableOperationStore`
   gained exactly one state slot (`self._record`), written by `commit_terminal`, read by
   `resolve_residual`. `resolve_residual` now raises `InvalidLifecycleTransitionError` when
   there is no open residual obligation, and returns `CLOSED` with the retained
   `terminal_commit` otherwise.
4. **Service guard** (`src/odoo_forge/durable_operations/service.py`) — `advance_lifecycle`
   gained a third guard (after regress guard and flip guard, order preserved) rejecting any
   transition into `SUCCEEDED`/`FAILED` from a non-terminal current state. The
   `SUCCEEDED->SUCCEEDED` / `FAILED->FAILED` idempotent carve-out (flip guard's
   `target is not current` condition) is preserved.
5. **Archived design correction** — append-only correction note inserted into
   `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` immediately after
   the Interfaces/Contracts table (after line 111). Line 110 (the four-action `RecoveryPlan`
   row) left byte-intact; diff review confirmed only additions, zero deletions/modifications.
6. **Final validation** — full quality gate green (see below). Diff touches exactly the six
   files listed in design.md's File Changes table. No adapter or workflow module imports
   `DurableOperationStore`/`DurableOperationRecord` outside `src/odoo_forge/ports/` and
   `tests/` (verified via ripgrep).

## Quality Gate (all green, in order)

1. `uv run lint-imports` — Contracts: 6 kept, 0 broken.
2. `uv run ruff check .` — All checks passed.
3. `uv run ruff format --check .` — 107 files already formatted (2 files reformatted during
   apply — pre-existing formatting drift in touched test files, unrelated to the fix logic).
4. `uv run mypy` (strict) — Success: no issues found in 104 source files.
5. `uv run pytest` — 460 passed, 1 deselected.

## Files Changed

- `src/odoo_forge/ports/durable_operation_store.py`
- `src/odoo_forge/durable_operations/service.py`
- `tests/ports/test_durable_operation_store.py`
- `tests/durable_operations/test_service.py`
- `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` (append-only)
- `openspec/changes/CAP-DURABLE-OPERATIONS-RECORD-FIX/tasks.md` (checkboxes marked)

## Deviations from Design

None. All four architecture decisions followed verbatim. Load-bearing constraints preserved:
- `cleanup_required lifecycle` substring kept verbatim in the first `__post_init__` error.
- Guard order in `advance_lifecycle`: regress -> flip -> new terminal-target check.
- No new error class added; `InvalidLifecycleTransitionError` reused.
- Fake gained exactly one state slot.
- Archive line 110 untouched; correction is append-only.
- Non-goals untouched: `COMPENSATE`, `TERMINAL_PENDING` wire-up, `UnknownOperationOutcomeError`.
- Hexagonal boundaries intact (`lint-imports` green); no port signature changes.

## Next Steps

Ready for `sdd-verify`.
