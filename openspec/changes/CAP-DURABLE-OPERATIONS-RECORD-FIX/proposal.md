# Proposal: Durable Operations Record Integrity Fix

## Intent and Outcome

Judgment Day (blind dual review) on merge `99053bd` (PR #53) found an audit-integrity defect in the
shipped `durable-operations` contract: a durable operation **loses its authoritative outcome and its
redacted evidence the moment residual cleanup is resolved**.

`DurableOperationRecord.__post_init__` accepts a `terminal_commit` only when the lifecycle is
`CLEANUP_REQUIRED` (residual non-empty) or equals `terminal_commit.outcome` (residual empty).
`LifecycleState.CLOSED` satisfies neither, so no conforming adapter can hold a `CLOSED` record that
still carries its terminal commit. The reference fake proves the consequence: `resolve_residual`
returns `CLOSED` with `terminal_commit=None`.

This contradicts the capability's own spec — *"the evidence MUST remain sufficient to support
recovery, reconciliation, or audit of the operation"* — inside a capability whose entire purpose is
durability and auditability. Fix it **now**, before any adapter exists.

## Scope

### In Scope
- Fix the `DurableOperationRecord` invariant so `CLOSED` is valid **only** as the resolution of a
  residual-cleanup terminal commit, with the `terminal_commit` retained. The empty-residual branch
  keeps requiring `lifecycle == terminal_commit.outcome`.
- Update the `resolve_residual` port docstring to state that closing preserves the terminal commit.
- Make the reference fake stateful enough to prove `CLOSED` retains outcome + evidence
  **behaviorally**, not by `inspect.signature`.
- Tighten `advance_lifecycle` so `SUCCEEDED`/`FAILED` are unreachable without evidence, forcing all
  terminal transitions through `build_terminal_commit`.
- Correct the archived `design.md` `RecoveryPlan` drift: `compensate` was never a recovery action.
- Add a `NO_RECOVERY_REQUIRED` recovery action. Once `CLOSED` legitimately carries a terminal
  commit, `plan_recovery` has no way to say "this operation is resolved" and falls through to
  `RECONCILE` (or `RESUME`) for finished work. The same hole already swallowed `SUCCEEDED`/`FAILED`.

### Non-Goals
- `COMPENSATE` as a `RecoveryAction` — no spec REQUIREMENT demands it, only the archived design
  drifted, and `plan_recovery` has no ownership input to decide it.
- `TERMINAL_PENDING` wire-up vs. removal — needs its own decision.
- `UnknownOperationOutcomeError` dead code — inert, no urgency.
- Behavioral coverage of every port method — this change proves the defect, not the whole surface.

## Product Rules

- A resolved cleanup obligation MUST NOT erase the authoritative terminal outcome or its evidence.
- A terminal outcome MUST NOT become authoritative without durable evidence.
- The port stays provider-neutral; hexagonal boundaries are enforced by import-linter.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `durable-operations`: terminal outcome and redacted evidence MUST survive residual-cleanup
  resolution (`CLOSED`); terminal lifecycle states MUST NOT be reachable without durable evidence.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/ports/durable_operation_store.py` | Modified | `__post_init__` invariant; `resolve_residual` docstring |
| `src/odoo_forge/durable_operations/service.py` | Modified | `advance_lifecycle` evidence gate |
| `tests/ports/test_durable_operation_store.py` | Modified | stateful reference fake + regression tests |
| `openspec/specs/durable-operations/spec.md` | Modified | delta requirements |
| `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` | Modified | drift correction |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Breaking contract change for future adapters | High (by design) | **Zero** adapters implement `DurableOperationStore` today; present blast radius is nil. Landing before adoption is the point. |
| A clean terminal record can never be `CLOSED` | Med | No code or spec need exists. The looser alternative (CLOSED as universal escape hatch) would hide the bug, not fix it. |
| Stateful fake destabilizes the `runtime_checkable` structural-typing test | Low | Keep the fake minimal; keep the Protocol conformance test intact. |
| Evidence gate on `advance_lifecycle` breaks existing pure-transition tests | Low | Strict TDD; `uv run pytest` green before merge. |

## Rollback

Revert the change branch. The contract has no consumers, so reverting restores the pre-fix (defective
but merged) behavior with no downstream migration.

## Success Criteria

- [ ] A `DurableOperationRecord` with `lifecycle=CLOSED` can carry its `terminal_commit`, including
      outcome and redacted evidence.
- [ ] The reference fake proves this behaviorally (constructed record, asserted fields) rather than by
      signature inspection.
- [ ] `advance_lifecycle` rejects evidence-free transitions to `SUCCEEDED`/`FAILED`.
- [ ] `plan_recovery` reports `NO_RECOVERY_REQUIRED` for a resolved operation instead of asking a
      workflow to resume or reconcile finished work.
- [ ] No compensation-triggering recovery action exists, and the archived design says so.
- [ ] `uv run pytest` green; import-linter boundaries unchanged.

## Traceability

Corrective follow-up to Judgment Day findings on merge `99053bd` (PR #53, `feat/cap-durable-operations`),
archived as `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/`.
