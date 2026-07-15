# Proposal: First Docker PostgreSQL Database Adapter

## Intent

Add the first concrete `DatabaseProvider`: an isolated Docker PostgreSQL adapter selected by `DPROV-DB`. It gives downstream work a proven provider implementation while preserving the current local backend and avoiding runtime cutover.

## Scope

### In Scope
- Implement the accepted provider lifecycle with adapter-owned Docker PostgreSQL resources, bounded availability checks, reconciliation, deletion, and cleanup.
- Consume credentials only through `CAP-CREDENTIALS`; keep plaintext out of provider values, commands, diagnostics, and evidence.
- Use `CAP-DATA-ARTIFACTS` references for every backup output or restore input handoff; validate restore readiness before mutation.
- Prove provisioning, availability, recovery, rollback, and ownership-scoped cleanup against real Docker.

### Out of Scope
- Extracting or rerouting the PostgreSQL owned by the local backend; `INT-DATABASE-RUNTIME-CUTOVER` remains separate.
- `WF-DATA-COPY`, `SP-CONTROL-PLANE-AUTHORITY`, `sp-data-environments`, or changes to PublishedLayer/Override semantics.
- Redefining provider-neutral credential, artifact, or database contracts.

## Capabilities

### New Capabilities
- `docker-postgresql-database-adapter`: Additive Docker PostgreSQL implementation of the accepted database lifecycle, ownership, credential, artifact, recovery, and evidence contracts.

### Modified Capabilities
- None.

## Approach

Create `src/odoo_forge_postgres_docker/` as a package-isolated adapter implementing `DatabaseProvider`. Track creator proof and mutate, recover, disable, or remove only resources created by the adapter. Reuse proven Docker readiness and created-only rollback patterns without coupling to `DockerBackendProvider`. Keep all contracts provider-neutral and runtime routing unchanged.

Delivery uses autonomous chained slices within the 400-line review budget.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_postgres_docker/` | New | Adapter and Docker command boundary |
| `tests/adapters/` | Modified | Contract, safety, recovery, artifact, and real-Docker evidence |
| `pyproject.toml` | Modified | Package, test, coverage, and import-boundary integration |
| `docs/specs/platform/portfolio.json` | Modified | Acceptance evidence only |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cleanup deletes backend or external data | Medium | Require creator proof and independently verify residuals |
| Secrets or artifact details leak | Medium | Opaque handles/refs, target-side injection, redacted diagnostics |
| Fake tests hide Docker failures | Medium | Opt-in real-Docker lifecycle evidence |

## Rollback Plan

Disable adapter selection and remove only adapter-owned resources using creation receipts. Leave the local backend, external/adopted resources, and runtime routing unchanged; report redacted residual cleanup failures.

## Dependencies

- Accepted `CAP-CREDENTIALS`, `CAP-DATA-ARTIFACTS`, and `PORT-DATABASE-PROVIDER` contracts.
- Accepted Roadmap Unit 1 real-Docker evidence and available Docker PostgreSQL prerequisites.

## Success Criteria

- [ ] Adapter conforms to `DatabaseProvider` without changing provider-neutral contracts.
- [ ] Real Docker proves provisioning, bounded availability, recovery, and complete ownership-scoped cleanup.
- [ ] Credential and artifact boundaries remain opaque and redacted.
- [ ] No local-backend extraction, runtime cutover, or unrelated workflow/policy change occurs.
