# Exploration — CAP-DURABLE-OPERATIONS-RECORD-FIX

## Origin

Judgment Day (blind dual review) on merge `99053bd` (PR #53, `feat/cap-durable-operations`)
surfaced defects in the shipped durable-operations contract. That change is merged and
archived; this is a corrective follow-up change.

## Current State

### Problem 1 — CLOSED records structurally erase their terminal outcome

`DurableOperationRecord.__post_init__` (`src/odoo_forge/ports/durable_operation_store.py:28-44`)
enforces exactly two branches:

- `terminal_commit.residual_cleanup` non-empty → lifecycle MUST be `CLEANUP_REQUIRED`
- `terminal_commit.residual_cleanup` empty → lifecycle MUST equal `terminal_commit.outcome`

`LifecycleState.CLOSED` satisfies neither branch. It is therefore structurally impossible to
construct a record with `lifecycle=CLOSED` that still carries its `terminal_commit`.

The consequence is proven by the reference fake at
`tests/ports/test_durable_operation_store.py:105-113`: `resolve_residual` returns
`lifecycle=CLOSED` with **no** `terminal_commit`, discarding the authoritative outcome and its
redacted evidence the moment residual cleanup resolves. Any conforming adapter is forced into
the same data loss.

This contradicts the capability's own governing spec
(`openspec/specs/durable-operations/spec.md`, "Redacted Durable Evidence"):
*"the evidence MUST remain sufficient to support recovery, reconciliation, or audit of the
operation."*

### Problem 2 — RecoveryAction drift is documentation-only

Contrary to the initial review framing, the spec and the code **already agree**.
`openspec/specs/durable-operations/spec.md` ("Workflow-Level Recovery and Reconciliation")
names only resume / reconcile / residual, matching the shipped `RecoveryAction` enum
(`src/odoo_forge/durable_operations/service.py:21-26`).

The drift exists only in the archived
`openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md:110`, which describes a
fourth `compensate` action that no spec REQUIREMENT demands and no code implements.

`CompensationScope` / `ensure_compensation_target` (`service.py:177-183`) are independent pure
functions a workflow calls directly to validate ownership before compensating.
`plan_recovery(state, revision, checkpoint, mutation_attempted)` has no ownership input, so it
structurally cannot decide `COMPENSATE` versus `SURFACE_RESIDUAL` today.

### Blast radius

No adapter anywhere implements `DurableOperationStore` or `DurableOperationRecovery`. The
contract has no consumers yet, so corrective changes are safe to land before adoption.

### Secondary gaps (confirmed, mostly deferred)

- `LifecycleState.TERMINAL_PENDING` is ordered in `_LIFECYCLE_ORDER` but is never a transition
  target anywhere in code or tests.
- `UnknownOperationOutcomeError` is defined and exported but never raised.
- `advance_lifecycle` can reach `SUCCEEDED` / `FAILED` with zero evidence; only
  `build_terminal_commit` enforces non-empty evidence, and nothing prevents a caller from
  bypassing it.
- The reference fake is stateless and only signature-checks `mark_reconciliation_required`,
  `resolve_residual`, and the replay-conflict path via `inspect.signature`.

## Approaches

### Problem 1

**Option A (recommended)** — `CLOSED` is reachable only as the resolution of a
residual-cleanup terminal commit:

- `residual_cleanup` non-empty → lifecycle in `{CLEANUP_REQUIRED, CLOSED}`
- `residual_cleanup` empty → lifecycle must still equal `outcome` (unchanged)

Pros: matches `resolve_residual`'s documented purpose; minimal change; does not weaken the more
common no-residual path. Cons: a no-residual record can never be marked `CLOSED` — nothing today
needs that. Effort: Low-Medium.

**Option B** — `CLOSED` as a universal escape hatch that bypasses all outcome/residual matching.

Pros: simpler; also covers closing a clean terminal record. Cons: weakens the invariant, allowing
incoherent outcome/residual combinations under `CLOSED`. Effort: Low.

### Problem 2

**Option A (recommended)** — correct `design.md` to three actions, matching the spec and the
code. Compensation remains a workflow-invoked primitive triggered after `SURFACE_RESIDUAL`.
Effort: Low (documentation only), zero behavior change.

**Option B** — add `COMPENSATE` to `RecoveryAction` and wire `plan_recovery` to return it.
Requires a signature change plus new spec REQUIREMENTs and scenarios. No workflow needs it today.
Effort: Medium-High. Scope creep.

## Recommendation

Problem 1 → Option A. Problem 2 → Option A. Additionally fix the `advance_lifecycle` evidence
bypass in this change: it is the same integrity concern as Problem 1 and is low effort.

## Scope Boundary

**In scope**

1. `DurableOperationRecord.__post_init__` invariant fix plus `resolve_residual` docstring.
2. A stateful-enough reference fake to behaviorally prove that `CLOSED` preserves
   `terminal_commit`, with new regression tests.
3. `design.md` `RecoveryPlan` drift corrected to three actions.
4. `advance_lifecycle` tightened so terminal outcomes are unreachable without evidence.

**Deferred to a separate change**

- `TERMINAL_PENDING` unused — needs its own wire-up-versus-remove decision.
- `UnknownOperationOutcomeError` never raised — inert, low urgency.
- Broadening the fake so every port method is behaviorally tested.
- Real `COMPENSATE` support — pending an actual workflow need and a new spec REQUIREMENT.

## Risks

- Option B for Problem 1 would disguise the bug rather than fix it.
- Option A blocks a currently nonexistent "close a clean terminal record" use case; acceptable,
  since no code or spec need was found.
- Making the fake stateful touches the `runtime_checkable` Protocol structural-typing reference
  test; the change must stay minimal.
- Tightening `advance_lifecycle` is a breaking API change for any future adapter. Zero adapters
  exist today, so present risk is nil — but the proposal must call it out explicitly.
