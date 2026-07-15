# Proposal: Docker Database Adapter Security Authority

## Intent and Outcome

Close accepted `review-e272dab2cf939ee5` findings: credentials in Docker `Config.Env`, inspect-reconstructible receipts, forgeable runtime evidence, and stale evidence. Use credential-safe injection and protected local authority that survives complete restarts from first delivery.

## Scope

### In Scope
- Inject PostgreSQL credentials through modern Docker Secrets/file mechanisms without `Config.Env` persistence.
- Store Docker ownership authority locally with restrictive permissions and integrity verification, without PostgreSQL credentials.
- Allow labels only as discovery identifiers; require authority verification for mutation, reconcile, rollback, and cleanup.
- Replace importable/process-local evidence minting with evidence verifiable through the durable authority.
- Make legacy resources fail closed and require recreation; old labels provide no migration authority.
- Regenerate verification/archive evidence against final lineage.
- Deliver through autonomous chained PRs, each within the 400-line review budget, independently verifiable and rollbackable.

### Non-Goals and Exclusions
- No provider-neutral contract changes, local-backend rerouting/cutover, tracker integration, control-plane authority, data environments, data copy, or PublishedLayer/Override work.
- No legacy-Docker compatibility that weakens modern secret handling.
- Never modify, recover, validate, reopen, or otherwise touch `review-093c1c067f361178`.

## Capabilities

### New Capabilities
- `docker-database-ownership-authority`: Durable Docker ownership custody and evidence verification.

### Modified Capabilities
- `docker-postgresql-database-adapter`: Require non-reconstructible ownership and credential-safe provisioning.
- `credential-materialization`: Require Docker target injection that leaves no plaintext credential in `Config.Env`.

## Security and Compatibility Invariants

- Missing, unreadable, tampered, or corrupt authority state MUST fail closed.
- Restarted rollback/cleanup may proceed only after authority-backed ownership verification.
- Docker inspection alone MUST never reconstruct ownership authority or mint acceptance evidence.
- `DatabaseProvider`, opaque handoffs, typed redaction, local-backend routing, and all exclusions remain unchanged.

## Approach and Unresolved Design Decisions

Use a backend-specific durable authority store and modern Docker secret injection. Design selects format/location, permissions, integrity/key custody, rotation, atomic recovery, replay semantics, and supported secret mechanism without embedding importable authority.

## Affected Areas

| Area | Impact |
|---|---|
| `src/odoo_forge_postgres_docker/` | Secret injection, authority custody, ownership checks |
| `src/odoo_forge/database/readiness.py` | Verifiable runtime evidence |
| `tests/` and final evidence | Security regressions and real-Docker proof |

## Rollout and Rollback

Roll out after authority initialization and real-Docker proof; recreate legacy resources. Roll back by chain slice without restoring label authority or environment credentials. Preserve verified authority state for cleanup; otherwise fail closed with a redacted ownership error.

## Risks and Success Criteria

- Store loss/corruption can strand resources; document operator recreation.
- Docker secret behavior varies; validate supported modern runtimes using real Docker.
- [ ] `docker inspect` exposes neither PostgreSQL credentials nor reconstructible authority.
- [ ] Restart, tamper, loss, rollback, cleanup, and forged-evidence tests prove fail-closed behavior.
- [ ] Final verification/archive evidence binds the completed chained lineage.
