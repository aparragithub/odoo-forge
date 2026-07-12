# Proposal: CAP-TENANCY

## Intent

Define `CAP-TENANCY` as the contract-first capability that establishes tenant identity, isolation boundaries, quota authority, ownership composition, and downstream handoffs for the platform. In this proposal, the canonical tenant is the **customer/client**. Project is a subordinate scope under that tenant, and request/environment classes such as PROD, QA, and DEV are operational classifications rather than alternative tenancy units.

## Scope

### In Scope
- Define the normative tenant model with **customer/client** as the canonical tenancy unit.
- Define subordinate scope relationships so project exists **under** a tenant boundary.
- Define request/environment classes such as PROD, QA, and DEV as operational classifications that consume tenancy rather than define it.
- Define the minimum isolation contract downstream consumers must honor when they accept tenant scope.
- Define how tenant authority composes with existing resource ownership semantics (`created`, `adopted`, `external`) without replacing them.
- Define quota authority exactly once at `CAP-TENANCY`, including what attaches to the tenant boundary and what downstream capabilities may only consume.
- Define explicit handoff rules so **SP-3**, **SP-4**, and **SP-8** consume `CAP-TENANCY` instead of redefining tenancy, isolation, or quota semantics.
- Define acceptance evidence for a readiness gate such as `AC-CAP-TENANCY-READY`.

### Out of Scope
- Auth, identity, session, or RBAC implementation.
- Provider-specific adapter behavior or target-native enforcement details.
- Control-plane persistence, API, or registry implementation.
- Lifecycle retention, garbage-collection, orphan-reclamation, or backup policy details.
- Project catalog implementation beyond the minimum terminology needed to describe subordinate scopes.

## Capabilities

### New Capabilities
- `tenancy-contract`: normative definition of tenant identity, subordinate scopes, isolation expectations, quota authority, ownership composition, and downstream consumption rules.

### Modified Capabilities
- None.

## Approach

Use a contract-first proposal anchored in the existing exploration, platform roadmap, and portfolio integrity rules. The change must establish one canonical answer to “who the tenant is” before any adapter, control-plane, or request workflow extends tenancy into implementation. `CAP-TENANCY` should define the boundary once, then require SP-3, SP-4, and SP-8 to accept tenant scope as input and apply their own responsibilities within that boundary.

This proposal stays deliberately narrow: it creates the prerequisite capability, not the control plane, not auth, and not provider enforcement logic. Quota must be authored exactly once here; downstream changes may evaluate or enforce quota decisions, but they may not redefine the quota model.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/changes/CAP-TENANCY/` | Modified | Proposal and follow-on planning artifacts for the tenancy capability |
| `openspec/specs/` | New | Canonical capability spec for tenancy contract and readiness gate |
| `docs/specs/platform/portfolio.json` | Modified | Portfolio dependency and acceptance alignment for `CAP-TENANCY` and downstream consumers |
| `docs/specs/platform/SP-3-remote-backend-providers.md` | Follow-up alignment | Must consume tenant isolation contract rather than define tenancy |
| `docs/specs/platform/SP-4-control-plane-core.md` | Follow-up alignment | Must consume tenant identity/isolation/quota contract rather than own it |
| `docs/specs/platform/SP-8-instance-lifecycle-requests.md` | Follow-up alignment | Must consume tenant/quota rules and remove quota redefinition |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tenant boundary expands into control-plane or auth scope | Med | Keep this capability contract-only and defer runtime implementation to dependent changes |
| Project or request/environment classes get treated as a competing tenancy unit | High | Make the customer/client rule explicit and normative in the spec and success criteria |
| Quota semantics get duplicated downstream | High | State that quota authority lives exactly once at `CAP-TENANCY`; downstream artifacts may only consume it |
| Ownership semantics conflict with current resource receipts | Med | Define composition with `created` / `adopted` / `external`, not replacement |
| Provider-native details leak into the capability | Med | Keep isolation rules provider-neutral and describe target-native enforcement as downstream work |

## Rollback Plan

Revert the `CAP-TENANCY` proposal/spec artifacts and keep SP-3, SP-4, and SP-8 blocked from tenancy-dependent design until a corrected contract is approved. No runtime rollback is needed because this proposal introduces planning authority, not product behavior.

## Dependencies

- `openspec/changes/CAP-TENANCY/exploration.md`
- `docs/specs/2026-07-08-platform-roadmap.md`
- `docs/specs/platform/portfolio.json`
- `openspec/specs/platform-portfolio-documentation-integrity/spec.md`
- `docs/specs/platform/SP-3-remote-backend-providers.md`
- `docs/specs/platform/SP-4-control-plane-core.md`
- `docs/specs/platform/SP-8-instance-lifecycle-requests.md`

## Success Criteria

- [ ] The accepted contract states that **tenant = customer/client** and rejects project or request/environment classes as peer tenancy units.
- [ ] The contract defines project as a subordinate scope under a tenant and treats PROD/QA/DEV as operational classifications rather than tenancy boundaries.
- [ ] The contract defines the minimum isolation boundary and ownership-composition rules required for downstream consumers.
- [ ] Quota authority is defined exactly once at `CAP-TENANCY`, and SP-3/SP-4/SP-8 are positioned as consumers rather than redefiners.
- [ ] `AC-CAP-TENANCY-READY` evidence is sufficient to unblock downstream spec/design work without introducing auth, provider-specific behavior, or control-plane implementation.

## Proposal Question Round

Questions to confirm during interactive review:
1. Should tenant identity be a platform-generated stable ID with customer/client as the business meaning, or is a customer/client slug itself expected to be the canonical external identifier?
2. Which request/environment classifications must be normative in v1 beyond `project`: only PROD/QA/DEV, or also lineage-specific distinctions such as QA-from-PROD?
3. When quota is defined at `CAP-TENANCY`, should the first slice only define attachment/evaluation semantics, or also define the initial quota dimensions that SP-8 and other consumers must reference?

Current assumptions if no corrections are made:
- Customer/client is the only canonical tenancy unit.
- Project is a nested scope, not an alternate authority.
- PROD/QA/DEV are operational classifications, not tenancy units.
- SP-3, SP-4, and SP-8 receive tenant scope and rules from `CAP-TENANCY` and do not redefine them.
- Runtime enforcement, persistence, and auth remain follow-up work.
