# Proposal: Durable Operations Capability

## Intent and Outcome

Long-running and crash-sensitive workflows in Odoo Forge need one reusable durability contract instead of rebuilding retry, recovery, cleanup, and audit behavior per workflow. The outcome of this change is a capability-first contract for durable operations: stable operation identity, monotonic lifecycle, durable checkpoints, authoritative terminal commit, recovery/reconciliation, ownership-aware compensation handoff, and redacted durable evidence.

## Scope

### In Scope
- Define a reusable durable operation lifecycle for accepted, in-flight, terminal, and cleanup-required work.
- Define idempotency and conflict rules for same-operation replay versus mismatched retry.
- Define checkpoint and receipt semantics needed for safe resume after crash.
- Define the authoritative terminal commit contract so success/failure, evidence, and cleanup obligations become visible atomically.
- Define recovery and reconciliation semantics for unknown-outcome and residual-cleanup cases.
- Define ownership-handoff and redacted durable evidence requirements that downstream workflows can reuse.

### Non-Goals
- Workflow-specific business rules for managed environments, copy orchestration, anonymization, or approvals.
- Database-provider-specific behavior beyond alignment with existing provider contracts.
- Full control-plane implementation, storage productization, or scheduling/retention policy.
- Choosing the final persistence adapter or absorbing unrelated operational policy.

## Product Rules and Safety Defaults

- The same operation identity with the same request meaning MUST replay safely; the same identity with different request meaning MUST fail as a conflict.
- Operation state MUST be monotonic; recovery MUST NOT require redoing an unsafe mutation blindly.
- Hidden or incomplete work MUST NOT become authoritative success.
- Terminal outcome, evidence, and cleanup obligations MUST commit together or remain non-authoritative.
- Compensation MUST remove only invocation-owned resources.
- Failed cleanup MUST become durable residual work, not best-effort logging.
- Durable evidence MUST be redacted: no secrets, connection material, or data bytes.

## Affected Areas

- `openspec/changes/CAP-DURABLE-OPERATIONS/` — proposal, spec, design, and tasks for the reusable capability.
- `openspec/changes/sp-data-environments/` — primary downstream consumer currently blocked on this contract.
- `openspec/specs/database-provider/spec.md` — alignment point for provider-level operation identity and reconciliation semantics.
- `src/odoo_forge/database/types.py` — existing ownership/receipt vocabulary to align with the new capability contract.
- `src/odoo_forge/data_artifacts/contracts.py` — existing residual/failure outcome patterns to compose with durable evidence.
- Future likely implementation area: `src/odoo_forge/durable_operations/` and provider-neutral persistence/recovery ports.

## Capability Shape

### New Capability
- `durable-operations`: reusable contract for idempotent lifecycle, checkpointed progress, authoritative terminal commit, recovery/reconciliation, ownership-aware compensation, and redacted durable evidence.

### Modified Capabilities
- None in this proposal. Downstream workflows adopt this contract in their own changes.

## Delivery Intent

Deliver the capability contract first so dependent changes can build on stable semantics without locking the project to one persistence implementation. Forced chained delivery and the 400-line review budget remain in effect for later implementation slices.

## Risks

| Risk | Mitigation |
|---|---|
| Capability is underspecified and workflows fork their own durability logic | Make lifecycle, idempotency, terminal commit, reconciliation, and evidence requirements explicit in spec/design. |
| Capability leaks into one storage/control-plane implementation | Keep proposal contract-first and defer adapter choices to later phases. |
| Crash windows still allow torn terminal visibility | Require atomic terminal publication of outcome, evidence, and cleanup obligations. |
| Residual cleanup becomes invisible operational debt | Model cleanup-required and residual obligations as durable first-class state. |
| Provider and workflow reconciliation semantics get conflated | Keep provider alignment explicit but define workflow-level recovery as a separate reusable contract. |

## Rollback

Rollback means not adopting the capability in downstream workflows until accepted implementation slices are complete. Any partial implementation must be independently revertible, leaving current workflow-specific behavior unchanged and preventing incomplete durable state from becoming authoritative.

## Success Criteria

- Downstream workflows have a clear reusable contract for operation identity, replay, conflict, checkpoints, terminal commit, recovery, and residual cleanup.
- The capability distinguishes provider-level reconciliation from workflow-level reconciliation cleanly enough for composition.
- The contract requires redacted durable evidence and ownership-safe compensation by default.
- `sp-data-environments` and similar consumers can proceed to spec/design without inventing their own durability model.
- Later implementation can be delivered in chained slices without reopening the product definition.
