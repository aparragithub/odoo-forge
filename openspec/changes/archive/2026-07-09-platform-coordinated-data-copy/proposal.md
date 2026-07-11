# Proposal: Platform Coordinated Data Copy

## Intent

Deliver SP-2's safe database-and-filestore copy transaction, initially production-to-QA.

## Scope

### In Scope
- Own the authoritative consistency lease/boundary; both captures consume it, and database creation consumes the captured database artifact. Validate the paired target and discard captures.
- Sequence production-to-QA first; preserve governance-defined dev, QA, and preprod behavior.
- Compensate only receipt-owned resources; durably persist typed residuals for idempotent retry/reconciliation.
- Add the copy CLI; close `GATE-012`, `GATE-013`, `GATE-018`, cross-child `INT-CLI-01`, and the copy halves of `INT-TX-AUDIT-01` and `INT-E2E-01`.

### Out of Scope
- Canonical provider internals; backend ownership migration; policy, audit, or governance-repository implementations; SP-10 scheduling, retention, or restore drills.

## Capabilities

### New Capabilities
- `coordinated-data-copy`: Lease-bound capture/restore, validation/discard, orchestration, compensation, residual reconciliation, and copy CLI.

### Modified Capabilities
- None.

Umbrella reconciliation delegates coordinated-copy requirements and `GATE-012/013/018` here. The parent `database-provider-lifecycle` retains cross-child acceptance, including `GATE-014` and final end-to-end proof, without duplicating child requirements.

## Approach

Consume provider-core refs, receipts, captures, and created-only deletion; require governance's immutable decision/start before mutation. Sequence lease → captures → resume → targets → validation → terminal handoff → discard. Governance makes the terminal audit and proposed binding durable atomically or returns a typed uncommitted failure; only success exposes a binding. Copy compensates an uncommitted outcome and persists residuals, so compensated resources cannot remain bound.

Use forced autonomous PR slices below 400 changed lines: (1) lease/capture contracts, (2) restore/validate/discard coordinator, (3) compensation/residual reconciliation, (4) CLI and cross-child integration. Tests and rollback stay with each slice.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/{database,ports}/` | New | Copy contracts and coordinator |
| `src/odoo_forge_cli/main.py` | Modified | Copy command/composition |
| `tests/{database,adapters,cli}/` | New | Gates, faults, integration |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Boundary mismatch | High | Lease-derived captures and artifact-consuming restore |
| Torn audit/binding | High | Commit-or-uncommitted governance handoff |
| Sensitive residuals | High | Durable typed residuals and idempotent reconciliation |

## Rollback Plan

Revert slices in reverse order; disable the copy CLI first. Reconcile persisted residuals before removing adapters, deleting only `created=True` resources and preserving sources/pre-existing targets.

## Dependencies and Relationships

- Depends on provider core #6314 and data governance #6318.
- Runtime integration #6323 is required for final CLI/network completion, not copy-domain implementation.
- Third downstream child of the four-child SP-2 umbrella.

## Success Criteria

- [ ] Same-boundary production-to-QA capture, artifact restore, validation, and discard pass.
- [ ] Fault injection proves no partial success, no binding to compensated resources, and recoverable residuals.
- [ ] Dev/preprod regressions, assigned gates, integration halves, and every sub-400-line slice pass.
