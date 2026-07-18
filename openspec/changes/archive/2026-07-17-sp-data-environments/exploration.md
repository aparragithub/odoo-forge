## Exploration: SP-DATA-ENVIRONMENTS — Managed Data Environments

### Current State

`SP-DATA-ENVIRONMENTS` is the outcome-first successor to the environment lifecycle portion of historical SP-2. Its business intent is to provide managed provision, clone, randomized non-production, and pre-production data environments for developers, QA/control-plane users, and delivery automation. The authoritative portfolio assigns data policy decisions `DD` and `DG` to this outcome and defines anonymization as the default for non-production data, with only explicit, justified, approved, and auditable QA/pre-production exceptions.

The portfolio is more authoritative than the preserved `SP-2-database-provider-and-lifecycle.md` brief and the archived `platform-database-provider*` planning artifacts. Those earlier artifacts bundled provider contracts, adapters, runtime ownership, governance, coordinated copy, and the actor-facing outcome; they were archived as superseded planning with no implementation, verification, or baseline spec sync.

No `DatabaseProvider`, database lifecycle domain, data artifact model, anonymization policy engine, coordinated copy workflow, or data-environment CLI exists in the current code. PostgreSQL is currently an internal part of the local Docker backend: `plan_backend()` hardcodes PostgreSQL 16 and local credentials, while `DockerBackendProvider` creates PostgreSQL and Odoo containers plus persistent database/filestore volumes. `stop()` preserves named volumes, and failed runs remove only resources created by that invocation. The manifest has no provider, source data, destination policy, or anonymization fields.

The current portfolio makes full outcome acceptance depend on three hard handoffs:

- `CHG-FIRST-DATABASE-ADAPTER` — itself gated by `PORT-DATABASE-PROVIDER`, `CAP-CREDENTIALS`, and `CAP-DATA-ARTIFACTS`.
- `WF-DATA-COPY` — gated by the first database adapter, `INT-DATABASE-RUNTIME-CUTOVER`, `CAP-DURABLE-OPERATIONS`, and `CAP-RESOURCE-OWNERSHIP`.
- `SP-CONTROL-PLANE-AUTHORITY` — the canonical pointer/lineage authority required before this outcome is complete.

Provider policy `DP`, tenancy policy `DT`, data policy `DD`, prerequisite activation policy `DG`, and `DPROV-DB` are decided. `DPROV-DB` selects Docker PostgreSQL as the exactly one first adapter because it reuses the existing tested local backend and minimizes initial delivery risk. No open or closed GitHub issue currently tracks `SP-DATA-ENVIRONMENTS` or its predecessor scope.

### Affected Areas

- `docs/specs/platform/portfolio.json` — authoritative scope transfers, decisions, hard dependencies, and acceptance handoffs.
- `docs/specs/platform/SP-2-database-provider-and-lifecycle.md` — historical intent and actor journeys; useful evidence but no longer the authoritative decomposition.
- `src/odoo_forge/ports/` — future `DatabaseProvider` contract, separate from the existing runtime `BackendProvider`.
- `src/odoo_forge/backend/plan.py` — currently owns PostgreSQL topology, credentials, and persistent-volume planning; runtime cutover must avoid duplicate database ownership.
- `src/odoo_forge_docker/provider.py` — current PostgreSQL creation, readiness, rollback, and volume-preservation behavior that any extraction must retain.
- `src/odoo_forge/manifest/schema.py` — currently contains no data-environment intent; any declarative additions require an explicit authority decision rather than ad hoc fields.
- `src/odoo_forge_cli/main.py` — current composition root and likely early operator boundary for lifecycle commands.
- `openspec/specs/local-backend/spec.md` — protects existing local PostgreSQL and filestore safety guarantees and explicitly excludes backup/restore and anonymization.
- `tests/backend/`, `tests/adapters/`, `tests/ports/`, and `tests/cli/` — future contract, policy, orchestration, safety-regression, and command-boundary coverage.
- `openspec/changes/archive/2026-07-09-platform-database-provider/` and related partial archives — reusable safety findings, but not active requirements or completed implementation.

### Approaches

1. **Dependency-led outcome delivery** — keep `sp-data-environments` focused on the managed-environment outcome and deliver its portfolio prerequisites as explicit, acceptance-gated changes before final outcome integration.
   - Pros: Preserves the new outcome-first portfolio; keeps provider, artifact, durability, ownership, workflow, and control-plane concerns independently owned; supports forced chained PRs under the 400-line budget; prevents superseded SP-2 scope from returning as a monolith.
   - Cons: Requires disciplined handoff specs and more than one SDD change before the outcome can be declared complete.
   - Effort: High overall, Medium per chained work unit.

2. **Local Docker vertical slice first** — implement provision/clone/randomize against the existing local PostgreSQL backend and defer control-plane integration.
   - Pros: Reuses the strongest current implementation and tests; lowers initial infrastructure cost; gives fast feedback on port and anonymization contracts.
   - Cons: Cannot satisfy the portfolio's full hard dependency on control-plane authority and risks coupling the outcome contract to the selected local Docker adapter.
   - Effort: High.

3. **Resurrect the historical SP-2 umbrella** — implement provider contract, adapter, runtime extraction, governance, coordinated copy, CLI, and outcome in one change.
   - Pros: One apparent delivery boundary and one end-to-end narrative.
   - Cons: Contradicts the authoritative portfolio decomposition, revives superseded artifacts, exceeds the review budget, creates unsafe ownership coupling, and makes rollback/review impractical.
   - Effort: Very High.

### Recommendation

Use **dependency-led outcome delivery**. The `sp-data-environments` proposal should define the actor-visible outcome, safe-default policy, acceptance handoffs, and exclusions without pretending that all prerequisites belong inside one implementation change. It should preserve the current hard dependency chain and name the independently activated prerequisites required now under `DG`, especially `CAP-DATA-ARTIFACTS`, `CAP-CREDENTIALS`, `PORT-DATABASE-PROVIDER`, the first database adapter, runtime ownership cutover, durable operations, resource ownership, coordinated copy, and control-plane authority.

Subsequent portfolio decision: `DPROV-DB` selected Docker PostgreSQL because working provisioning and safety tests already exist, minimizing initial delivery risk. This resolves only the adapter choice; implementation of this outcome must not start until accepted evidence exists for `CHG-FIRST-DATABASE-ADAPTER`, `WF-DATA-COPY`, and `SP-CONTROL-PLANE-AUTHORITY`. Every implementation slice must use the forced chained-PR strategy and remain within the 400 authored-line review budget.

### Constraints, Edge Cases, and Open Questions

- Database and Odoo filestore data form one logical environment; success must never expose mismatched snapshots or partial lineage.
- Failed or retried operations must delete only invocation-owned targets, preserve sources and pre-existing volumes, persist residual cleanup work, and remain idempotent.
- Non-production anonymization is the default. Any real-production-data exception needs actor, reason, source, destination, approval, and result evidence durable enough for audit.
- The control plane must store references and lineage, never database or filestore bytes.
- Provider-native snapshots and logical dump/restore have different consistency, portability, anonymization, cost, and testability tradeoffs; the chosen adapter determines the first concrete strategy.
- Scheduling, retention, backup policy, and restore drills belong to `SP-DATA-RECOVERY`, not this change.
- Request approval/UI, production governance, CI/CD orchestration, and developer onboarding consume this outcome but remain outside its implementation scope.
- Open before implementation: define the first `CAP-DATA-ARTIFACTS` capture/ref contract; assign anonymization-rules ownership and transformations; define approval authority and durable audit storage; decide the smallest control-plane handoff needed for the first usable environment; and accept evidence for all three required handoffs.

### Risks

- The portfolio dependency graph is larger than the historical brief suggests; treating the outcome as one coding change would hide prerequisite work and exceed the review budget.
- Extracting PostgreSQL from `BackendPlan` can create duplicate ownership or delete preserved data unless the cutover is additive and receipt-driven.
- Database-only copying can create unusable Odoo environments when filestore consistency is ignored.
- The selected Docker PostgreSQL first adapter can leak provider-specific assumptions into outcome contracts unless the provider-neutral boundary is enforced.
- Audit, compensation, and binding commits can tear across crashes unless terminal-state recovery is specified before orchestration implementation.
- Historical documents still use SP-2 terminology and contain superseded dependency claims, which can mislead downstream proposal authors unless authority is stated explicitly.

### Ready for Proposal

Yes. The business outcome, authoritative scope, current implementation seam, hard dependencies, safety constraints, and out-of-scope boundaries are clear enough to propose `sp-data-environments`. The proposal must remain outcome-level, record Docker PostgreSQL as the decided first adapter without treating prerequisite handoffs as accepted, and plan prerequisite delivery through forced chained PRs rather than collapsing the portfolio into one oversized change.
