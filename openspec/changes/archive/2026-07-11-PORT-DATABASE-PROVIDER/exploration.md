## Exploration: PORT-DATABASE-PROVIDER — Database Provider Port

### Current State

`docs/specs/platform/portfolio.json` is the normative planning authority. It defines `PORT-DATABASE-PROVIDER` as a proposed provider port owned by Data Platform. Transfer `X7` moves only `provider.contract` from historical `SP-2` into this port. The portfolio defines no incoming dependency edge for the port and one outgoing hard edge, `G17`, to `CHG-FIRST-DATABASE-ADAPTER`, handed off through `AC-PORT-DATABASE-PROVIDER-READY`.

The portfolio decisions attached to the port are settled: `DP` selects one adapter globally at initialization, `DG` activates prerequisites independently when a concrete consumer needs them, and `DPROV-DB` selects Docker PostgreSQL as the first database adapter. The selected adapter constrains the first consumer, not the provider-neutral port. No unresolved product-selection decision currently blocks this port.

The acceptance gate is not yet an executable contract. `AC-PORT-DATABASE-PROVIDER-READY` remains `proposed`, has no evidence, and carries only gap `G3` (`No provider contract exists`). The portfolio does not define accepted operations, value types, credential and data-artifact boundaries, ownership semantics, or failure taxonomy. The active downstream exploration for `CHG-FIRST-DATABASE-ADAPTER` requires those exact handoffs before adapter proposal/spec work can begin, but it does not select their shapes. `CAP-CREDENTIALS` and `CAP-DATA-ARTIFACTS` are parallel hard inputs to that adapter; the portfolio does not make them dependencies of this port.

Production code has no `DatabaseProvider`, database domain package, or database-port tests. PostgreSQL remains embedded in `BackendPlan` and `DockerBackendProvider`, which currently own PostgreSQL 16 topology, local credentials, readiness, invocation-created rollback, and persistent-volume preservation. Existing ports establish a runtime-checkable `Protocol` and package-isolation pattern, but they do not determine this port's database lifecycle API.

The historical `SP-2` brief and all five database planning archives are non-normative evidence: `platform-database-provider`, `platform-database-provider-core`, `platform-database-data-governance`, `platform-database-runtime-integration`, and `platform-coordinated-data-copy`. They bundled or proposed detailed signatures, refs, credentials, artifacts, adapters, policy, runtime cutover, and copy orchestration. The portfolio redefinition superseded that decomposition; the archives were not implemented, verified, or merged into canonical OpenSpec specs. Their four-method protocol and companion contracts therefore remain candidates, not current requirements.

### Affected Areas

- `docs/specs/platform/portfolio.json` — normative identity, ownership transfer, decisions, status, acceptance gate, and downstream hard edge.
- `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/exploration.md` — active consumer statement of the exact handoff categories needed from this port.
- `src/odoo_forge/ports/` — future provider-neutral protocol boundary; currently no database provider exists.
- `src/odoo_forge/database/` — possible home for provider-neutral values only if the approved contract assigns them here; currently absent.
- `tests/ports/` — existing runtime protocol-conformance pattern; exact database conformance criteria remain unapproved.
- `src/odoo_forge/backend/plan.py` and `src/odoo_forge_docker/provider.py` — current embedded PostgreSQL behavior, useful as compatibility evidence but outside this port's ownership.
- `openspec/changes/archive/2026-07-09-platform-database-provider/` — superseded umbrella planning; evidence only.
- `openspec/changes/archive/2026-07-09-platform-database-provider-core/` — superseded detailed port/adapter contract; evidence only.
- `openspec/changes/archive/2026-07-09-platform-database-data-governance/` — superseded policy/audit allocation; outside this port unless reassigned by the portfolio.
- `openspec/changes/archive/2026-07-09-platform-database-runtime-integration/` — superseded runtime-cutover allocation; outside this port.
- `openspec/changes/archive/2026-07-09-platform-coordinated-data-copy/` — superseded workflow allocation; outside this port.

### Approaches

1. **Contract-first re-baseline** — obtain Data Platform approval for the provider-neutral handoff, then create a new port-only proposal/spec under the current portfolio.
   - Pros: Preserves current authority and ownership; gives the adapter an explicit stable contract; avoids reviving unrelated SP-2 scope.
   - Cons: Cannot advance until the missing contract choices and acceptance statement are approved.
   - Effort: Medium

2. **Explicitly promote selected historical candidates** — review individual archived signatures and values, accept or reject each under the new portfolio, and record fresh decision evidence before proposal.
   - Pros: Reuses substantial analysis without treating it as authoritative by default.
   - Cons: Requires deliberate re-approval; archived contracts couple credentials, artifacts, ownership, and adapter concerns that now have separate owners.
   - Effort: Medium

3. **Rehydrate `platform-database-provider-core` unchanged** — treat the archived core proposal/spec/design as the port contract.
   - Pros: Provides immediately detailed APIs and tests.
   - Cons: Violates supersession and current ownership, combines the port with a Docker adapter and parallel prerequisite contracts, and would silently invent current requirements.
   - Effort: High, with high rework risk

### Recommendation

Use **contract-first re-baselining**. Keep this change limited to transfer `X7`: the provider-neutral contract and the evidence required to satisfy `AC-PORT-DATABASE-PROVIDER-READY`. Do not absorb the Docker PostgreSQL adapter, credential implementation, data-artifact implementation, runtime cutover, destination policy, coordinated copy, CLI workflow, or managed-data-environment outcome.

Before proposal, Data Platform must approve a normative handoff statement covering the exact provider operations and provider-owned values; how the contract refers to, but does not implement, credential materialization and database artifacts; creation/adoption/deletion ownership semantics; typed failures; and what conformance evidence satisfies the gate. This is an architecture-contract blocker, not an unresolved provider-selection decision. Historical contracts may be cited as options only after each element is explicitly re-approved.

The accepted proposal/spec must also define how evidence is attached to `AC-PORT-DATABASE-PROVIDER-READY`. Under the portfolio status rules, the port cannot move from `proposed` to `validated` until an approved contract exists, and the downstream adapter must remain blocked until the gate has accepted evidence.

### Risks

- Copying the archived four-method API would convert superseded planning into requirements without current approval.
- Pulling `CAP-CREDENTIALS` or `CAP-DATA-ARTIFACTS` into this change would contradict the portfolio's independent ownership and adapter dependency graph.
- Letting Docker PostgreSQL details shape the port can make the contract provider-specific despite the first-adapter decision.
- Omitting ownership, cleanup, or typed failure semantics leaves the adapter unable to prove safe conformance.
- Treating current backend-owned PostgreSQL as an adapter would create false acceptance evidence and obscure the later runtime cutover.
- `AC-PORT-DATABASE-PROVIDER-READY` currently has no normative behavioral acceptance text, so status cannot be advanced safely from repository evidence alone.

### Ready for Proposal

No. Scope, ownership, decisions, dependency direction, superseded artifacts, and the required handoff categories are clear, but the normative provider contract and gate acceptance statement are missing. The exact blocker is Data Platform approval of the operations, values, cross-capability reference boundaries, ownership/cleanup semantics, typed failures, conformance evidence, and evidence-recording rule for `AC-PORT-DATABASE-PROVIDER-READY`. No unresolved product-selection decision needs to be made, and no code should be implemented before that contract is approved.
