## Exploration: CHG-FIRST-DATABASE-ADAPTER — First Database Adapter

### Current State

`CHG-FIRST-DATABASE-ADAPTER` is an implementation-sized prerequisite in the authoritative platform portfolio, not the managed-data-environments outcome and not the database runtime cutover. `DPROV-DB` is decided: the first and currently single platform database adapter is Docker PostgreSQL because it reuses the tested local Docker implementation and minimizes initial delivery risk. Provider selection (`DP`) and destination data policy (`DD`) are also decided; no product choice remains open for selecting this adapter.

The change has three hard inputs: `PORT-DATABASE-PROVIDER`, `CAP-CREDENTIALS`, and `CAP-DATA-ARTIFACTS`. All three now have accepted canonical specs, provider-neutral source, and focused tests recorded in `docs/specs/platform/portfolio.json`. The product choices are also resolved, so this change is ready for proposal rather than blocked on a placeholder. These inputs define contracts only; they do not provide the concrete database adapter.

Current production code includes `DatabaseProvider`, its provider-neutral database values, opaque credential materialization, and data-artifact contracts. It still has no standalone PostgreSQL adapter package. PostgreSQL is embedded in `BackendPlan` and `DockerBackendProvider`: the adapter creates the network, database/Odoo containers, and named database/filestore volumes. Existing behavior provides useful implementation evidence—readiness via `pg_isready`, invocation-created rollback, and preservation of pre-existing named volumes—but it owns an entire local Odoo runtime rather than implementing `DatabaseProvider`.

Archived `platform-database-provider*` artifacts contain detailed candidate contracts and a Docker PostgreSQL design, but they were superseded, unimplemented, unverified, and never merged into canonical specs. They are evidence and risk input only; copying their signatures, artifact shape, or credential mechanism into this change would invent current requirements.

### Affected Areas

- `docs/specs/platform/portfolio.json` — authoritative identity, selected adapter, hard dependency edges, acceptance handoff, and downstream consumers.
- `src/odoo_forge/ports/database_provider.py` — accepted `DatabaseProvider` contract that the adapter must implement.
- `src/odoo_forge/database/`, `src/odoo_forge/credentials/`, and `src/odoo_forge/data_artifacts/` — accepted provider-neutral values and contracts consumed by the adapter.
- `src/odoo_forge_postgres_docker/` — expected isolated Docker PostgreSQL adapter package based on repository adapter conventions and archived evidence; currently absent.
- `src/odoo_forge/backend/plan.py` — current embedded PostgreSQL topology and credentials; evidence only because runtime ownership cutover is a separate downstream change.
- `src/odoo_forge_docker/provider.py` — current readiness, rollback, and volume-preservation behavior that establishes safety regressions to avoid.
- `pyproject.toml` — future package discovery, coverage, and import-boundary enforcement for an isolated adapter.
- `tests/ports/`, `tests/adapters/`, and future database model tests — contract/signature conformance, command safety, ownership, recovery, artifact, credential-redaction, and real-Docker proof.
- `openspec/specs/local-backend/spec.md` — protects existing backend-owned PostgreSQL behavior until `INT-DATABASE-RUNTIME-CUTOVER`; this change must remain additive.

### Approaches

1. **Gate-first additive adapter** — accept the three prerequisite contracts, then implement Docker PostgreSQL in an isolated adapter package without changing current runtime routing.
   - Pros: Follows the authoritative dependency DAG; avoids inventing contracts; preserves current local runtime; gives runtime cutover and data-copy consumers a stable acceptance handoff; supports autonomous chained slices.
   - Cons: This change cannot proceed to a reliable proposal/spec until prerequisite artifacts and acceptance evidence exist.
   - Effort: High overall; Medium per chained slice.

2. **Rehydrate the superseded provider-core plan** — reuse archived protocol signatures, credential leases, artifact refs, and Docker lifecycle behavior as current requirements.
   - Pros: Detailed prior analysis could accelerate drafting.
   - Cons: Violates the current portfolio authority, recombines prerequisite ownership, and risks implementing obsolete contracts that no accepted consumer owns.
   - Effort: High, with high rework risk.

3. **Extract PostgreSQL directly from the local backend** — refactor `BackendPlan` and `DockerBackendProvider` while adding the adapter.
   - Pros: Removes duplicate PostgreSQL mechanics immediately.
   - Cons: Absorbs `INT-DATABASE-RUNTIME-CUTOVER`, threatens existing volume/data guarantees, couples adapter acceptance to Odoo runtime behavior, and exceeds one coherent review boundary.
   - Effort: Very High.

### Recommendation

Use the **gate-first additive adapter**. The three prerequisite handoffs are now accepted and define the provider operations and values, credential-handle/materialization boundary, artifact/reference and consistency contract, ownership/cleanup semantics, and typed failure expectations. Create this change's proposal and delta spec from those canonical contracts without expanding their ownership.

Once unblocked, implement Docker PostgreSQL additively and package-isolated. Preserve existing local backend ownership until the separately planned `INT-DATABASE-RUNTIME-CUTOVER`. Reuse proven safety patterns as implementation evidence, not as implicit requirements. Because adapter delivery is expected to exceed the 400 authored-line review budget, retain `force-chained` delivery with autonomous contract-conformance, non-mutating command boundary, lifecycle, recovery/cleanup, artifact, and real-Docker verification slices.

### Risks

- Drafting before prerequisite acceptance would silently turn superseded archive details into new requirements.
- Sharing resource names or deletion behavior with the current backend can create duplicate ownership or delete preserved data.
- Secrets can leak through Docker argv, environment, errors, refs, or test fixtures unless the accepted credential contract closes each boundary.
- Artifact restore can reconnect to a live source or mutate a target before integrity verification unless the accepted artifact contract is explicit.
- A fake-only adapter suite can pass while Docker readiness, rollback, recovery, and ownership behavior remains unsafe.
- Treating the accepted provider-neutral contracts as a concrete adapter would conceal the remaining operational implementation and integration work.

### Ready for Proposal

Yes. Adapter selection and all three prerequisite acceptance handoffs are resolved. Proposal work must use the canonical specs and current contracts as authority; the concrete adapter, runtime cutover, and managed-data workflows remain absent and must not be claimed as delivered.
