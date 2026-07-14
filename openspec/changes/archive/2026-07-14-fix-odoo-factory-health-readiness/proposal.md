# Proposal: Bootstrap Fresh Odoo Databases Before Readiness

## Intent

Make `DockerBackendProvider.run()` initialize Odoo's core schema before starting the long-running server for a database lifecycle created by that invocation. Runtime evidence after 300 seconds (`unhealthy`, `KeyError: 'ir.http'`, missing `ir_module_module`) proves timeout tuning alone cannot repair an uninitialized database.

## Scope

### In Scope
- Run a temporary one-shot Odoo container with `-i base --stop-after-init --no-http` only when this invocation creates the PostgreSQL data lifecycle.
- Remove the bootstrap container after success, then start normal Odoo and retain Docker health as readiness authority.
- Fail before normal Odoo startup when bootstrap fails; capture redacted evidence and perform created-only rollback without preserving the bootstrap container.
- Keep the completed 300-second readiness/recovery and timeout diagnostics work as defense-in-depth for post-bootstrap startup failures.
- Prove acceptance with the unchanged real-Docker baseline and factory smoke harnesses.

### Out of Scope
- Repairing or adopting pre-existing incomplete databases.
- CLI, manifest, environment-variable, or backend-port configuration changes.
- Factory image, entrypoint, healthcheck, or baseline harness changes.
- The baseline's mutable-image-tag warning; it remains a baseline-SDD follow-up.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `local-backend`: require provider-owned fresh-database bootstrap before normal Docker-health readiness.

## Approach

Use creation of the planned PostgreSQL data volume as the provider's database-newness authority. A distinct temporary container reuses the planned Odoo image, network, mounts, filestore, environment, and opaque credential injection, but overrides the command for base-only initialization. Successful removal precedes normal server creation. Any bootstrap failure records bounded redacted logs, removes the temporary container, and rolls back only resources created by this invocation.

## Affected Areas

| Area | Impact |
|---|---|
| `src/odoo_forge_docker/provider.py` | Bootstrap orchestration, identity, cleanup, diagnostics |
| `tests/adapters/test_docker_provider.py` | Strict-TDD lifecycle, argv, failure, ownership tests |
| `tests/adapters/test_docker_provider_integration.py` | Unchanged acceptance evidence |

## Delivery and Risk

Completed prerequisite slices remain Child #1 (readiness/recovery) and Child #2 (diagnostics/redaction). New Child #3 is the autonomous bootstrap slice; Phase 3 acceptance follows it. Primary risks are initializing an existing database, leaking secrets, or leaving a temporary container; creation authority, mandatory redaction, collision refusal, and ordered cleanup mitigate them.

## Rollback Plan

Revert Child #3 provider/tests only. Retain completed readiness and diagnostics defenses; do not alter factory, harness, or historical apply evidence.

## Success Criteria

- [ ] Fresh lifecycle bootstraps only `base`, removes the temporary container, and reaches normal Docker health.
- [ ] Existing lifecycles are never initialized, repaired, or adopted by bootstrap.
- [ ] Bootstrap failure prevents normal startup and leaves no invocation-created resources or secrets.
- [ ] Unchanged baseline and factory smoke pass.
