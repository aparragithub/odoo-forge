## Exploration: SP-2 — DatabaseProvider + DB lifecycle

### Current State
The canonical change name is `platform-database-provider`, taken directly from `docs/specs/platform/SP-2-database-provider-and-lifecycle.md`. SP-2 is a new Layer-1 ports-and-adapters change, independent of SP-1 and dependent only on the completed Slice 4b foundation.

The documented scope is: define a runtime-checkable `DatabaseProvider` port with `provision`, `clone`, `randomize`, and `drop`; add `DatabaseRef`, target specifications, and pure anonymization rules; deliver one adapter selected at initialization from Dockerized PostgreSQL, AWS RDS, or VPS PostgreSQL; expose foundation-level lifecycle CLI operations; support QA clones, randomized DEV copies, and anonymized pre-production copies; add package/import boundaries and port-signature plus adapter integration tests. Database contents remain provider-owned; core stores only connection/credential references and lineage metadata. Real production data is exceptional and requires explicit, audited authorization. Dump/restore and anonymization primitives belong to SP-2, while scheduling, retention, backup orchestration, and restore drills belong to SP-10.

Explicit non-goals are runtime mixing of database backends, Odoo schema ownership, control-plane state/registry, and request approval workflows. The roadmap lists all three database adapters as candidates, but the detailed SP-2 brief scopes the first change to **one** chosen adapter; implementing all three is not required by this change.

No `DatabaseProvider`, database domain model, lifecycle use case, adapter, CLI command, baseline OpenSpec database spec, or dedicated test exists today. Slice 4b currently embeds local PostgreSQL inside `BackendPlan` and `DockerBackendProvider.run()`: it hardcodes `postgres:16`, deterministic local credentials, a named PG data volume, readiness checks, created-only rollback, and stop-time volume preservation. The only database-facing CLI behavior is implicit inside `forge run`.

### Affected Areas
- `src/odoo_forge/ports/` — add the provider contract while preserving the interface-only core boundary.
- `src/odoo_forge/` database domain modules — add immutable refs/specs, typed errors, lineage, pure lifecycle policy, and anonymization rules.
- `src/odoo_forge/backend/plan.py` — remove or reshape the current assumption that every backend plan owns a local PostgreSQL container and credentials.
- `src/odoo_forge_docker/provider.py` — separate existing local PostgreSQL provisioning from backend runtime ownership without regressing readiness, rollback, or persistent-volume safety.
- `src/odoo_forge_cli/main.py` — compose the one selected database adapter and expose resilient lifecycle commands.
- New sibling database-adapter package — execute the chosen Dockerized PostgreSQL, RDS, or VPS strategy without leaking infrastructure imports into core.
- `pyproject.toml` — register the adapter package and add its import-linter forbidden contract/root package.
- `tests/ports/`, new database-domain tests, `tests/adapters/`, and `tests/cli/` — cover protocol signatures, safe defaults, lifecycle semantics, integration round-trips, diagnostics, and local-backend regressions.
- `tests/backend/test_plan.py` and `tests/adapters/test_docker_provider.py` — protect the existing PG env, readiness ordering, rollback, and pre-existing-volume guarantees during extraction.

### Approaches
1. **Dockerized PostgreSQL first, full SP-2 contract** — extract the proven Slice 4b database behavior into the new port/adapter, then implement clone, anonymize, drop, and pre-production-copy flows with logical PostgreSQL primitives.
   - Pros: Reuses the strongest current code and tests; lowest infrastructure and credential risk; validates the port and pure anonymization model locally.
   - Cons: Native snapshot behavior and the urgent RDS secrets decision remain for a later adapter; extracting ownership from `DockerBackendProvider` is delicate.
   - Effort: High

2. **AWS RDS first, full SP-2 contract** — make the first adapter production-oriented and use RDS snapshot/restore capabilities for clone and pre-production copies.
   - Pros: Directly serves the likely managed-production path; exercises provider-native clone semantics and credential handles immediately.
   - Cons: Requires an explicit secrets-store decision, AWS authentication/configuration, expensive integration fixtures, and a safe anonymization execution environment before the local ownership seam is simplified.
   - Effort: High

3. **Keep SP-2 as an umbrella and partition delivery into four child changes** — preserve the canonical outcome while giving provider lifecycle, runtime ownership, governance, and coordinated copy independent design and verification boundaries.
   - Pros: Resolves the overloaded parent design, isolates safety contracts, and supports reviewable chained PRs.
   - Cons: Requires explicit handoffs and umbrella-level integration acceptance so no requirement disappears between children.
   - Effort: High overall, Medium per child

### Recommendation
Keep `platform-database-provider` as the SP-2 umbrella and replace its single implementation design with exactly four child changes. Use Dockerized PostgreSQL first. The partition below is authoritative for child proposals: one owner per parent requirement or open finding, explicit handoffs, and umbrella-level acceptance only where behavior necessarily crosses children.

### Partition Map

The current blocking set is exactly `GATE-012..018`. Earlier JDA rows still marked `open` are superseded operationally by the Round 2 approval and later verified remediation entries; warnings remain informational.

#### Child boundaries

| Child | Capability owner | Depends on | First deliverable | Explicit exclusions | Handoff contract | Why a sub-400-line PR chain is viable |
|---|---|---|---|---|---|---|
| `platform-database-provider-core` | Exact canonical `DatabaseProvider`; immutable refs/specs/lineage; typed lifecycle errors; creator receipts; Docker PostgreSQL lifecycle adapter and package boundary | Slice 4b only | Protocol/models/errors plus runtime/signature conformance tests | Backend routing, destination policy/audit, filestore coordination, copy CLI | Stable refs, capture-compatible database artifact type, creation receipt, and typed errors consumed by all children | Contracts/models, adapter provision/drop, clone/randomize, and packaging/integration can be separate testable PRs |
| `platform-database-runtime-integration` | PostgreSQL ownership extraction; Odoo-only `BackendProvider`; PostgreSQL runtime control; merged status, reachability, network ownership, legacy adoption, and existing run/status/stop/logs/exec routing | Provider core | Additive composite status/runtime seams and legacy discovery tests while current `run` remains valid | Copy policy, durable audit, capture/restore orchestration, copy command | Supplies resolved database refs, runtime role status, network creator receipts, and legacy `created=False` adoption to the final CLI composition | Additive models, runtime adapters, routing/legacy compatibility, then atomic ownership cutover form rollback-safe PRs |
| `platform-database-data-governance` | Source classification; destination policy; authorization decisions; complete durable audit records; aggregate/binding persistence and crash recovery | Provider core | Pure dev/qa/preprod policy plus authorization-denial audit-schema tests | Database/filestore byte movement, runtime ownership, SP-10 scheduling/retention/control-plane audit | Returns an immutable authorization/policy decision; accepts operation outcomes and aggregate bindings; guarantees durable records and recoverable commit semantics | Pure policy/schema, durable append adapter, and journaled repository can be independently fault-tested PRs |
| `platform-coordinated-data-copy` | Shared consistency lease; DB/filestore capture, captured-artifact creation, validation/discard; copy coordinator; compensation, residual persistence/retry/reconciliation; final copy CLI | Provider core + data governance; runtime integration required only for completion at the CLI/network boundary | Fake-driven coordinator proving both captures share one boundary and DB creation consumes the capture | Provider implementation internals, backend ownership migration, universal anonymization, scheduling/retention/restore drills | Consumes core refs/receipts, governance decision/audit/repository, and runtime network/instance resolution; emits one validated aggregate or an explicit residual outcome | Capture ports, happy path, compensation/reconciliation, and CLI/Docker integration are autonomous PR slices |

#### Parent requirement allocation

| Parent requirement | Sole owner |
|---|---|
| `database-provider-lifecycle`: Provider contract and references | `platform-database-provider-core` |
| `database-provider-lifecycle`: Dockerized PostgreSQL lifecycle | `platform-database-provider-core` |
| `database-provider-lifecycle`: Coordinated copy consistency | `platform-coordinated-data-copy` |
| `database-provider-lifecycle`: Destination policy, authorization, and audit | `platform-database-data-governance` |
| `database-provider-lifecycle`: Lifecycle command boundary | `INT-CLI-01` cross-child acceptance |
| `local-backend`: `run()` provisions its own Postgres when none is external | `platform-database-runtime-integration` |
| `local-backend`: run/status/stop/logs/exec commands enforce a resilient boundary | `platform-database-runtime-integration` |

#### Open finding allocation

| Finding | Sole owner | Required closure |
|---|---|---|
| `GATE-012` | `platform-coordinated-data-copy` | Database target creation consumes `DatabaseCaptureRef`, never a live source ref; both captures prove the same lease boundary. |
| `GATE-013` | `platform-coordinated-data-copy` | Explicit validation and capture-discard provider operations exist and are exercised on success/failure paths. |
| `GATE-014` | `INT-TX-AUDIT-01` cross-child acceptance | Governance and copy define one recoverable terminal transition: audit-result failure cannot leave compensated resources with a live committed binding. |
| `GATE-015` | `platform-database-data-governance` | Aggregate/binding persistence uses a journal or recoverable backup protocol for failures after replace/fsync. |
| `GATE-016` | `platform-database-runtime-integration` | Exact Odoo+PostgreSQL status merge, reachability-probe owner/timeout, and compatible typed errors are executable. |
| `GATE-017` | `platform-database-data-governance` | Audit schema always includes actor, reason, source, destination, result; authorization denial is durably recorded before return. |
| `GATE-018` | `platform-coordinated-data-copy` | Cleanup aggregates residuals, persists them durably, supports idempotent retry, and exposes reconciliation. |

#### Cross-child integration acceptance

- **`INT-CLI-01` — configured-provider command boundary:** after runtime integration and coordinated copy, the composition root selects one database provider; lifecycle/copy commands never mix providers; existing backend commands preserve single-line typed errors and resource ownership. This is the sole owner of the parent lifecycle-command requirement.
- **`INT-TX-AUDIT-01` — terminal-state atomicity:** data governance owns durable audit/repository primitives and coordinated copy owns compensation. Their joint failure matrix must prove every post-mutation path ends in either a committed validated aggregate with durable result or an unbound/rolled-back aggregate with durable residuals. This is the sole owner of `GATE-014`.
- **`INT-E2E-01` — umbrella success:** an authorized production-to-QA Docker flow yields matching validated DB/filestore lineage, complete audit fields, merged runtime status, and created-only cleanup without altering source or pre-existing resources.

#### Dependency DAG and proposal order

```text
Slice 4b
   |
   v
platform-database-provider-core
   |-----------------------------|
   v                             v
platform-database-data-governance  platform-database-runtime-integration
   |                             |
   |-------------+---------------|
                 v
platform-coordinated-data-copy
                 |
                 v
INT-CLI-01 + INT-TX-AUDIT-01 + INT-E2E-01
```

There is no runtime↔copy cycle: runtime integration exposes database/network/instance handoffs without importing the copy coordinator; coordinated copy may be designed against those ports after core+governance, but cannot be declared complete until the runtime-backed CLI acceptance passes. Data governance depends only on core refs and never on copy implementation types.

Proposal order: **(1) provider core, (2) data governance and runtime integration in parallel after core, (3) coordinated data copy, (4) umbrella integration acceptance.** If proposals must be strictly sequential, use core → data governance → runtime integration → coordinated data copy; runtime and governance are otherwise independent.

### Risks
- Existing local PostgreSQL provisioning is coupled to `BackendPlan` and `DockerBackendProvider`; extraction can cause duplicate ownership or data-loss regressions.
- A child may accidentally duplicate a shared model; child proposals must import only the owning child's handoff contracts.
- Governance/result durability and copy compensation can still tear state unless `INT-TX-AUDIT-01` is specified before either implementation is finalized.
- The runtime cutover can temporarily break `forge run`; keep it additive until provider composition and legacy adoption pass together.
- The umbrella exceeds 400 lines by design; every child still requires forced chained PRs and line-count checks per autonomous deliverable above.

### Ready for Proposal
Yes. Create child proposals in the dependency order above, without rewriting the umbrella proposal yet. Each proposal must copy its owned requirements/findings, name its handoff contracts and exclusions, retain Dockerized PostgreSQL as the first adapter, and commit to forced chained PRs under the 400-line review budget.
