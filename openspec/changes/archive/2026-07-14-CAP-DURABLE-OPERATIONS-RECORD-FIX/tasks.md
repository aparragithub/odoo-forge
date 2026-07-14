## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150 additions + deletions |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk (confirmed: single PR) |
| Chain strategy | none |

Decision needed before apply: No
Chained PRs recommended: No — design's own forecast (`design.md`, "Changed-Line Forecast") totals ~150
lines across two source files, two test files, the delta spec, and one append-only archive note; all
land together as one provider-neutral contract fix with zero adapters affected. This confirms the
orchestrator's Low-risk forecast; no contest.

## Delivery Boundaries

- Keep this change contract-only: no adapter or workflow consumer wiring.
- Single review-safe slice; strict TDD in every step: RED → GREEN → REFACTOR.
- Keep tests with the behavior they verify; do not split tests away from code.
- Do not edit `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` line 110 in
  place — append-only correction note only (Design Decision 4).

## 1. Slice 1 — Record invariant: CLOSED retains its terminal commit

- [x] RED: Add `test_record_retains_terminal_commit_when_residual_cleanup_is_closed` to
      `tests/ports/test_durable_operation_store.py` — construct a `DurableOperationRecord` with
      `lifecycle=CLOSED` and a `terminal_commit` carrying non-empty `residual_cleanup`; assert it is
      accepted and `terminal_commit.outcome` / `terminal_commit.evidence` are still visible on the
      record. Run `uv run pytest tests/ports/test_durable_operation_store.py` and confirm this test
      fails against current `__post_init__`.
- [x] RED: Add `test_record_rejects_closed_lifecycle_without_residual_cleanup` to the same file —
      construct a record with `lifecycle=CLOSED` and a `terminal_commit` whose `residual_cleanup` is
      empty; assert `pytest.raises(ValueError, match="terminal outcome lifecycle")`. Confirm it fails
      (currently raises a different message or accepts incorrectly).
- [x] GREEN: Edit `src/odoo_forge/ports/durable_operation_store.py` — add the module-level
      `_RESIDUAL_LIFECYCLES = frozenset({LifecycleState.CLEANUP_REQUIRED, LifecycleState.CLOSED})`
      constant and rewrite `DurableOperationRecord.__post_init__`'s residual branch to check
      `self.lifecycle not in _RESIDUAL_LIFECYCLES` per the design's exact predicate (design.md:37-58).
      Keep the first raised message containing the substring `cleanup_required lifecycle` verbatim so
      `test_record_rejects_terminal_outcome_lifecycle_when_residual_cleanup_exists`
      (`tests/ports/test_durable_operation_store.py:250`) stays green unchanged. Leave the
      empty-residual branch (`lifecycle == terminal_commit.outcome`) untouched.
- [x] GREEN: Run `uv run pytest tests/ports/test_durable_operation_store.py` and confirm all four
      record-invariant tests pass (the two new RED tests plus the two existing regression tests at
      `:250` and `:262`).
- [x] REFACTOR: Review naming/typing of the new constant and branch only; no behavioral drift. Re-run
      `uv run pytest tests/ports/test_durable_operation_store.py`.

*Satisfies: spec.md "Residual Cleanup Visibility" — scenarios "Resolved cleanup retains the terminal
outcome and evidence", "A closed record with no terminal work is still valid", "Closed records without
residual cleanup keep the unchanged invariant".*

## 2. Slice 2 — Port docstring: `resolve_residual` states retention and the no-op-is-an-error rule

- [x] GREEN: Edit `src/odoo_forge/ports/durable_operation_store.py` — replace the `resolve_residual`
      Protocol method docstring with the design's exact text (design.md:79-93): state that closing
      resolves the obligation, MUST NOT erase the terminal commit, the returned record has
      `lifecycle=CLOSED` and retains `terminal_commit`, and that `InvalidLifecycleTransitionError` is
      raised when the record carries no open residual obligation (closing is not a no-op).
- [x] TRIANGULATE: Run `uv run pytest tests/ports/test_durable_operation_store.py` — docstring-only
      change; confirm no test regresses.

*Satisfies: spec.md "Residual Cleanup Visibility" (documents the contract that Slices 1, 3 make true
in code).*

## 3. Slice 3 — Reference fake: one stateful slot proves CLOSED retention and rejects a no-op close

- [x] RED: Add `test_resolving_residual_cleanup_preserves_the_authoritative_terminal_outcome` to
      `tests/ports/test_durable_operation_store.py` — using a single `_ConformingDurableOperationStore`
      instance, call `commit_terminal(operation_id, _terminal_bundle(residual_cleanup=(residual,)))`
      then `resolve_residual(operation_id, <next revision>)`; assert the returned record has
      `lifecycle=CLOSED` **and** `terminal_commit == <the same bundle>` (behavioral, not
      `inspect.signature`). Confirm it fails against the current stateless fake (`resolve_residual`
      at `:105-113` returns `terminal_commit=None`).
- [x] RED: Add `test_resolving_residual_without_an_open_obligation_is_rejected` to the same file —
      call `resolve_residual` on a fresh `_ConformingDurableOperationStore` instance that never had
      `commit_terminal` called; assert `pytest.raises(InvalidLifecycleTransitionError)`. Confirm it
      fails (current fake returns a `CLOSED` record unconditionally).
- [x] GREEN: Edit `tests/ports/test_durable_operation_store.py` — add exactly one state slot
      `self._record: DurableOperationRecord | None = None` to `_ConformingDurableOperationStore.__init__`
      (design.md:135). Make `commit_terminal` write `self._record = <the record it builds>` before
      returning it. Rewrite `resolve_residual` per the design's exact implementation (design.md:144-163):
      guard revision, raise `InvalidLifecycleTransitionError` when `self._record` is `None` or its
      `terminal_commit` is `None`, raise the same error when `terminal_commit.residual_cleanup` is
      empty, otherwise return a new record with `lifecycle=CLOSED` and `terminal_commit=committed.terminal_commit`
      (retained). Leave `create_or_load`, `save_checkpoint`, `mark_reconciliation_required`,
      `list_recoverable`, and `_guard_revision` stateless and unchanged.
- [x] GREEN: Run `uv run pytest tests/ports/test_durable_operation_store.py` and confirm both new
      tests pass and every existing test in the file still passes, including
      `test_store_contract_exposes_replay_checkpoint_cas_residual_and_recovery_queries` (Protocol
      structural-typing test — must be unaffected by the fake's added `__init__` attribute) and
      `test_record_keeps_checkpoint_and_terminal_visibility_distinct` (fresh-instance isolation).
- [x] REFACTOR: Review the fake's new state handling for minimality (exactly one slot, two access
      points) per Design Decision 5; no additional statefulness. Re-run
      `uv run pytest tests/ports/test_durable_operation_store.py`.

*Satisfies: spec.md "Residual Cleanup Visibility" — scenario "Resolved cleanup retains the terminal
outcome and evidence" (behavioral proof); Design Decision 2 (error, not silent no-op).*

## 4. Slice 4 — Service: `advance_lifecycle` rejects evidence-free terminal transitions

- [x] RED: Add `test_lifecycle_rejects_evidence_free_terminal_outcomes` to
      `tests/durable_operations/test_service.py`, parametrized over
      `current ∈ {ACCEPTED, IN_PROGRESS, RECONCILIATION_REQUIRED, TERMINAL_PENDING}` ×
      `target ∈ {SUCCEEDED, FAILED}` (design.md:233) — call `advance_lifecycle(current, revision, target)`
      and assert `pytest.raises(InvalidLifecycleTransitionError)` for every combination. Run
      `uv run pytest tests/durable_operations/test_service.py` and confirm it fails against the
      current two-guard implementation.
- [x] GREEN: Edit `src/odoo_forge/durable_operations/service.py` — insert the third guard into
      `advance_lifecycle`, **after** the existing regress guard and flip guard (order is load-bearing
      per design.md:98-107):
      `if target in _TERMINAL_OUTCOMES and current not in _TERMINAL_OUTCOMES: raise InvalidLifecycleTransitionError(...)`.
      Do not touch the existing regress guard or the flip guard (`current in _TERMINAL_OUTCOMES and
      target in _TERMINAL_OUTCOMES and target is not current`) — the `SUCCEEDED→SUCCEEDED` /
      `FAILED→FAILED` idempotent carve-out MUST remain reachable through the flip guard's `target is
      not current` condition.
- [x] GREEN: Run `uv run pytest tests/durable_operations/test_service.py` and confirm the new
      parametrized test passes and all four existing `advance_lifecycle` tests still pass, in
      particular `test_lifecycle_rejects_flipping_a_published_terminal_outcome` (:70) and
      `test_lifecycle_keeps_terminal_outcomes_re_advanceable_towards_cleanup_and_closure` (:86) — the
      latter fails if the idempotent carve-out is lost.
- [x] REFACTOR: Review the new guard's placement and error message wording only; no behavioral
      drift. Re-run `uv run pytest tests/durable_operations/test_service.py`.

*Satisfies: spec.md "Authoritative Terminal Commit" — scenario "Evidence-free terminal transition is
rejected".*

## 5. Slice 5 — Archived design correction (append-only, audit-trail-safe)

- [x] Edit `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` — insert the
      correction note block from design.md:177-184 immediately after the Interfaces/Contracts table
      (after line 111, before the `Provider alignment:` heading). Do **not** modify line 110 (the
      `RecoveryPlan` row listing four actions) or any other existing line — this is an append-only
      audit-trail correction per `skills/_shared/openspec-convention.md:120` (Design Decision 4).
- [x] Verify with a diff review that only new lines were added to the archived file and zero existing
      lines were changed or removed.

*Satisfies: spec.md "Workflow-Level Recovery and Reconciliation" — scenario "Recovery actions are
limited to three" (documentation correction; code and spec already agree per exploration.md).*

## 6. Final cross-change validation

- [x] Run the full quality gate: `uv run lint-imports`, `uv run ruff check .`,
      `uv run ruff format --check .`, `uv run mypy`, `uv run pytest`. All must pass with zero
      failures and zero new warnings.
- [x] Confirm no adapter or workflow module imports `DurableOperationStore` or
      `DurableOperationRecord` outside `src/odoo_forge/ports/` and `tests/` — this change stays
      contract-only (Non-Goals, proposal.md).
- [x] Confirm the diff touches exactly the files listed in design.md's "File Changes" table:
      `src/odoo_forge/ports/durable_operation_store.py`,
      `src/odoo_forge/durable_operations/service.py`,
      `tests/ports/test_durable_operation_store.py`,
      `tests/durable_operations/test_service.py`,
      `openspec/changes/CAP-DURABLE-OPERATIONS-RECORD-FIX/specs/durable-operations/spec.md`,
      `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md`.
