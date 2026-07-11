# Proposal: Platform Database Data Governance

## Intent

Make production-derived copy decisions safe and crash-recoverable without owning data movement.

## Scope

### In Scope
- Classify sources as `production_derived|non_production`; canonical policy makes dev randomization mandatory with no bypass, while qa/preprod default to anonymization and permit only explicit, audited, destination-limited bypass.
- Immutable authorization decisions and durable denial before return.
- Complete audit records (`actor`, `reason`, `source`, `destination`, `result`) with fail-closed durable append/fsync.
- Durable aggregate/binding persistence with journal/backup recovery after replace or directory-fsync failure.
- Close `GATE-015`, `GATE-017`, and the governance half of `INT-TX-AUDIT-01`.

### Out of Scope
- Database/filestore movement, providers, backend runtime ownership, copy coordinator/CLI, and compensation.
- SP-10 scheduling, retention, control-plane workflows, approval workflows, and restore drills.

## Capabilities

### New Capabilities
- `database-data-governance`: Production-derived data policy, authorization, durable audit, and recoverable aggregate/binding state.

### Modified Capabilities
- None.

Umbrella reconciliation delegates the parent `database-provider-lifecycle` policy/authorization/audit requirement here; the parent retains only cross-child acceptance.

## Approach and Handoffs

Keep policy and schemas pure; place durable audit and journaled repositories behind core ports. Forced tested slices, each under 400 changed lines: (1) policy/authorization, (2) audit append, (3) repository recovery, (4) cross-child contracts.

Coordinated copy consumes an immutable decision and mutates only after durable authorization/start recording. It submits the terminal outcome and proposed aggregate/binding. Governance MUST NOT expose a binding before the matching terminal audit is durable. Typed uncommitted failure returns control to copy, which owns compensation/residuals; governance owns audit/repository recovery. This is its half of `INT-TX-AUDIT-01`.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/database/` | New | Pure policy, decisions, records |
| `src/odoo_forge/ports/` | New | Audit/repository finalization ports |
| `tests/{database,adapters}/` | New | Policy and fault-injection coverage |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Torn audit/binding state | High | Journal recovery; no binding before durable result |
| Bypass scope expands | Med | Closed destination enum and policy matrix |
| Cross-child contract drifts | Med | Shared terminal-state acceptance matrix |

## Rollback Plan

Revert additive slices before coordinator adoption; preserve audit/journal files read-only for recovery and forensics. No copy resources are touched by rollback.

## Dependencies and Relationships

- Depends on `platform-database-provider-core` refs, lineage, operation identity, and typed outcomes.
- Upstream of `platform-coordinated-data-copy`; independent of runtime integration.

## Success Criteria

- [ ] Policy/bypass and durable-denial tests pass.
- [ ] Every record has all five fields; append failures fail closed (`GATE-017`).
- [ ] Replace/fsync fault recovery preserves one valid prior-or-new state (`GATE-015`).
- [ ] `INT-TX-AUDIT-01` contract tests and every sub-400-line slice pass.
