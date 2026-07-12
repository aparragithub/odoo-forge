# Exploration: CAP-TENANCY

## Quick answer
`CAP-TENANCY` should solve a cross-cutting platform gap: the roadmap expects tenant-scoped isolation, ownership, and quotas, but the codebase still has only project/instance naming and resource-level ownership. There is no accepted contract for what a tenant is, how downstream capabilities refer to one, what must be isolated per tenant, or where quotas/ownership authority live.

The safest first move is a **contract-first capability**, not an implementation slice. Define tenant identity, isolation boundaries, quota authority, and ownership handoffs so remote deployment, control-plane authority, managed data environments, resource lifecycle, and request flows stop inventing their own tenant model.

## Business / problem framing
The platform vision is multi-client and actor-driven:
- onboarding requests environments **by client**;
- control-plane users request PROD / QA / DEV instances;
- remote backends must isolate instances per tenant;
- data workflows, quotas, and lifecycle policies must know who owns what.

Today that business story is ahead of the implementation model. Without an explicit tenancy capability, each downstream change risks choosing a different answer to questions like:
- Is a tenant a customer, a project, an environment family, or an account?
- What is isolated per tenant: network, namespace, database credentials, registry state, request state, audit scope?
- Who is allowed to consume quota or delete shared resources?
- How do ownership receipts relate to tenant boundaries?

If this stays implicit, the platform will accumulate incompatible boundaries across SP-3, SP-4, SP-8, resource lifecycle, and data environments.

## Existing tenancy-related concepts in the repo
### Planning / OpenSpec evidence
- `openspec/changes/archive/2026-07-10-platform-subproject-redefinition/exploration.md`
  names `CAP-TENANCY` as a new prerequisite for **tenant identity, isolation contract, quotas, and ownership boundaries**.
- `docs/specs/platform/SP-3-remote-backend-providers.md`
  requires **per-tenant data-plane isolation** and says adapters enforce a tenancy model defined elsewhere.
- `docs/specs/platform/SP-4-control-plane-core.md`
  lists **tenancy / isolation model** as an open requirement for the control plane.
- `docs/specs/platform/SP-8-instance-lifecycle-requests.md`
  still mentions quotas per role/client, which reinforces that request workflows consume quota policy but should not define it.
- `openspec/specs/platform-portfolio-documentation-integrity/spec.md`
  and the archived redefinition exploration explicitly say **quota occurs exactly once at `CAP-TENANCY`**.

### Current code concepts that are adjacent, but not tenancy yet
- `src/odoo_forge/manifest/schema.py`
  has a `Client` model, but it only captures local project paths (`addons_path`, `python_requirements`). It is not a tenant identity or isolation contract.
- `src/odoo_forge/backend/plan.py`
  derives runtime names from `manifest.name` and `instance`; this gives deterministic naming, not tenant semantics.
- `src/odoo_forge/database/types.py`
  already defines **resource ownership** (`created`, `adopted`, `external`). This is useful input for tenancy, but it is resource-local authority, not tenant boundary policy.
- `src/odoo_forge/credentials/types.py` and `materialization.py`
  show another successful cross-cutting pattern: opaque handles, explicit capability ownership, and target-scoped materialization. `CAP-TENANCY` should likely follow the same contract-first style.

### Important absence
Repo searches found **no tenant model, tenant ID type, quota policy type, tenant-aware registry state, or tenant-aware provider contract** in `src/` or `tests/`.

## Likely scope boundaries
### In scope
- Define the canonical **tenant identity** used by downstream capabilities.
- Define the **minimum isolation contract** downstream systems must honor.
- Define where **quotas/limits** live and what they attach to.
- Define how **tenant boundary** interacts with existing resource ownership receipts.
- Define acceptance evidence/gate for “tenancy readiness” so dependent changes can block on it.

### Out of scope
- Auth/RBAC implementation and role enforcement.
- Full control-plane persistence/API work.
- Provider-specific runtime implementation for every adapter.
- Data anonymization policy details.
- TTL/retention/orphan reclamation mechanics from resource lifecycle.
- Project catalog implementation details, unless strictly needed to name an upstream identity source.

## Recommended capability shape
Treat `CAP-TENANCY` as a **platform contract capability**.

It should answer, at minimum:
1. **Identity** — what stable identifier represents a tenant?
2. **Boundary** — which resources and state must be isolated by that identifier?
3. **Ownership** — when a resource receipt says `created/adopted/external`, how does that map to tenant authority?
4. **Quota** — what is metered, at what scope, and who evaluates it?
5. **Handoff** — how do SP-3, SP-4, SP-8, data environments, and lifecycle consume the contract without redefining it?

## Candidate first slices
### Slice A — Tenancy contract + readiness gate
Create the normative capability only:
- tenant identity value(s);
- isolation/ownership/quota rules;
- explicit downstream handoffs;
- acceptance gate such as `AC-CAP-TENANCY-READY` with executable/documentary evidence.

**Why first:** lowest risk, breaks the documented dependency cycle, and matches how `CAP-CREDENTIALS` / `PORT-DATABASE-PROVIDER` were turned into small prerequisite capabilities.

### Slice B — First-consumer scoping rules for local/first adapters
After Slice A, add only the smallest downstream surface needed so current foundations can carry tenant scope without implementing the whole control plane. For example:
- tenant-aware naming/scoping rules for backend/database/credential consumers;
- explicit “caller supplies tenant scope” boundaries;
- no auth, no registry, no orchestration.

**Why second:** gives concrete adoption pressure without collapsing CAP-TENANCY into SP-3 or SP-4.

## Risks
- **Wrong unit of tenancy.** Customer vs project vs environment family is a product decision with architectural consequences.
- **Boundary bleed.** Auth, project catalog, resource lifecycle, and control plane can easily leak into this capability.
- **Provider leakage.** Defining tenancy in Docker/Kubernetes/AWS terms would make the contract non-portable.
- **Quota duplication.** If SP-8 or lifecycle redefines limits, the portfolio rule “quota exactly once at CAP-TENANCY” breaks.
- **Ownership mismatch.** Existing resource ownership semantics are per-resource; tenancy must compose with them, not overwrite them.
- **No Engram read access in this execution context.** Only OpenSpec and repository evidence were available for exploration; Engram discoveries can be saved but not queried here.

## Recommendation
Frame `CAP-TENANCY` as: **the capability that defines who a tenant is, what must be isolated per tenant, how quotas are evaluated, and how tenant authority composes with resource ownership.**

Do **not** start from adapter code. Start from the contract and acceptance gate, then let downstream capabilities consume it.

## Ready for proposal
Yes — if the proposal stays contract-first and forces the unresolved product decision about the unit of tenancy. The proposal should avoid implementation promises beyond the minimal handoff needed by dependent changes.
