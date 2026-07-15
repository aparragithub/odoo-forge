# Proposal: Database Adapter Verification Closure

## Intent

Close two strict-verification gaps in the first Docker PostgreSQL adapter: an opaque credential-file cleanup residual can be hidden after successful container rollback, and acceptance lacks runtime proof that missing or simulated real-Docker/ownership evidence fails closed.

## Scope

### In Scope
- Surface any `credential-file` cleanup residual through the existing typed rollback-incomplete outcome, even when container rollback succeeds.
- Preserve rollback receipts, resource residuals, causal errors, and redaction; expose only the safe opaque `credential-file` identifier.
- Add deterministic acceptance-policy coverage at the existing readiness boundary for missing or simulated real-Docker/ownership evidence.

### Out of Scope
- Provider-neutral API changes or new error families.
- Portfolio mutation/governance, control-plane authority, runtime cutover, local PostgreSQL extraction, `WF-DATA-COPY`, `sp-data-environments`, or PublishedLayer/Override changes.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `docker-postgresql-database-adapter`: Make rollback residual reporting explicit for failed credential-file cleanup and require fail-closed runtime acceptance evidence.

## Approach

Extend the adapter's existing rollback decision to raise `RollbackIncompleteError` when either receipt-owned container residuals or credential cleanup residuals remain. Keep `credential-file` as the sole public cleanup token and retain the original failure as cause. Extend the pure readiness test seam with otherwise complete evidence that omits or simulates the required real-Docker/ownership marker; acceptance must remain false.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_postgres_docker/provider.py` | Modified | Propagate opaque cleanup residuals. |
| `tests/adapters/test_postgres_docker_provider.py` | Modified | Cover persistent unlink failure and redaction. |
| `tests/database/test_readiness.py` | Modified | Prove fail-closed acceptance policy. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Paths or secrets leak through residual diagnostics | Low | Assert only the allow-listed opaque token is observable. |
| Follow-up drifts from parent PR4 seams | Medium | Integrate PR4 first, then rebase and revalidate targeted behavior. |

## Rollback Plan

Revert this follow-up as one chained delivery unit, restoring parent PR4 behavior without changing provider-neutral contracts or parent artifacts.

## Dependencies

- `CHG-FIRST-DATABASE-ADAPTER` through PR4 MUST integrate first; this follow-up branches from that integrated commit and must not merge before it.

## Success Criteria

- [ ] Any opaque credential-file cleanup residual produces the existing rollback-incomplete outcome while preserving receipt and cause.
- [ ] Observable errors contain neither credential paths nor secret values.
- [ ] Missing or simulated real-Docker/ownership evidence deterministically leaves acceptance false.
