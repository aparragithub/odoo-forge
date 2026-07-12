# Design: CAP-TENANCY

## Technical Approach

Keep `CAP-TENANCY` contract-first, provider-neutral, and prerequisite-only.

This change defines the normative platform contract for:
- canonical tenant identity (`tenant_id` for the customer/client tenant),
- the only normative subordinate scope in v1 (`project`),
- operational classifications (`PROD` / `QA` / `DEV`) as non-tenancy metadata,
- the minimum tenant isolation boundary,
- composition with existing ownership semantics (`created` / `adopted` / `external`), and
- quota authority exactly once at `CAP-TENANCY`.

It does **not** design auth, RBAC, persistence, APIs, registry schemas, provider runtime behavior, or control-plane orchestration. Those consumers must accept this contract as input.

**Review boundary:** document and verify the contract, the downstream handoff shape, and the readiness gate `AC-CAP-TENANCY-READY`. No provider adapter or control-plane implementation is part of this design.

## Architecture Decisions

| Decision | Choice | Alternative / tradeoff | Rationale |
|---|---|---|---|
| Canonical tenancy unit | Tenant means customer/client | Project, environment family, provider account, or backend target as tenant | The proposal/spec require one normative answer before downstream work can proceed. |
| Canonical technical identifier | `tenant_id` is the stable technical identifier | Customer slug or provider-native identifier as canonical ID | Keeps business naming separate from stable technical scope and prevents provider leakage. |
| Subordinate scope model | `project` is the only normative subordinate scope in v1 and belongs to exactly one tenant | Multiple peer subordinate scopes in v1 | Minimizes ambiguity and keeps first-slice authority simple. |
| Operational classification model | `PROD` / `QA` / `DEV` are request/runtime classifications only | Treat environment family or lifecycle class as tenancy authority | Preserves the approved boundary that operations consume tenancy but do not define it. |
| Isolation definition | Define isolation as outcomes consumers must preserve across tenant-owned state, access surfaces, and provider-facing resources | Define isolation in Docker/Kubernetes/cloud-specific terms | Keeps the contract portable and lets SP-3 enforce it target-natively later. |
| Ownership composition | Tenant authority composes with `created` / `adopted` / `external`; it does not replace them | Replace resource ownership labels with tenant-only ownership | Existing resource receipts already carry meaning that downstream work depends on. |
| Quota authority | Define quota attachment/evaluation authority exactly once here | Let SP-3, SP-4, or SP-8 define local quota semantics | Prevents duplicate authority and preserves one normative quota source. |
| Downstream contract style | Consumers receive explicit tenant-scope inputs and are forbidden from redefining the model | Let each consumer infer tenancy from local context | Explicit handoff is the only way to stop semantic drift across SP-3/SP-4/SP-8. |
| Delivery | Documentation/spec/portfolio alignment first; implementation slices later consume the contract | Mix this change with control-plane or provider runtime work | Keeps reviewable scope small and preserves prerequisite status. |

## Conceptual Model

```text
Customer/Client
  -> Tenant
       tenant_id  (canonical technical identifier)
       labels     (optional business/display metadata; non-authoritative)

Tenant
  -> ProjectScope[*]
       project is valid only as child scope of exactly one tenant

TenantScope + ProjectScope?
  -> OperationalClassification
       PROD | QA | DEV
       consumes scope; never creates a new tenancy boundary

TenantScope + OwnershipKind
  -> OwnershipBinding
       created | adopted | external
       preserves existing ownership semantics inside tenant authority

TenantScope
  -> QuotaAuthority
       attachment/evaluation semantics defined once here
       consumers may evaluate/enforce/report, never redefine
```

### Normative invariants

- `tenant_id` is the canonical technical identifier for the customer/client tenant.
- Project cannot exist as a free-standing authority; it is always subordinate to one tenant.
- `PROD`, `QA`, and `DEV` never create new tenancy units.
- `environment_family` is not a normative v1 concept.
- Isolation is defined at the tenant boundary first; consumers may tighten it, never weaken it.
- Ownership labels remain meaningful and must be carried with tenant relationship, not collapsed into it.
- Quota authority originates once at `CAP-TENANCY` and is consumed downstream.

## Downstream Handoff Contract

### Required conceptual inputs

Every downstream consumer that operates on tenant-scoped behavior must receive a handoff equivalent to this conceptual shape:

| Input | Purpose | Owned by CAP-TENANCY? | Consumer may redefine? |
|---|---|---|---|
| `tenant_id` | Canonical tenant scope | Yes | No |
| tenant business label/metadata (optional) | Human-facing display/context only | Yes | No |
| `project` reference (optional, child-only) | Subordinate scoping inside one tenant | Yes | No |
| operational classification (`PROD`/`QA`/`DEV`) | Lifecycle/runtime behavior inside existing scope | Shared vocabulary | No |
| ownership relationship (`created`/`adopted`/`external`) | Resource authority composition | Shared vocabulary | No |
| quota context / outcome input contract | Tenant-level quota attachment/evaluation source | Yes | No |

### Consumer boundaries

| Consumer | Must receive | May own | Must NOT own |
|---|---|---|---|
| SP-3 remote backend providers | `tenant_id`, optional project scope, operational classification, isolation expectations | Target-native enforcement details for already-defined boundaries | Tenant identity, quota model, alternate tenancy units, provider-specific tenant semantics as the platform contract |
| SP-4 control plane core | `tenant_id`, project relationship, ownership composition, quota source contract | Orchestration, registry workflows, reconciliation, request plumbing | Canonical tenant definition, project-only authority, auth-by-proxy tenancy rules |
| SP-8 instance lifecycle requests | `tenant_id`, optional project scope, operational classification, quota input contract | Request shapes, approval flow, lifecycle verbs inside tenant scope | Per-role/per-client quota authority, alternate tenant definitions, environment class as tenancy |

The rule is simple: downstream systems may own **behavior within tenant scope**, but they may not own **the meaning of tenant scope**.

## Data / Decision Flow

```text
CAP-TENANCY contract
  -> defines tenant identity + subordinate scope + operational-class vocabulary
  -> defines minimum isolation outcomes
  -> defines ownership composition rules
  -> defines quota authority and consumption rules
  -> publishes readiness evidence (AC-CAP-TENANCY-READY)
       |
       +-> SP-3 consumes tenant scope to enforce isolation target-natively
       +-> SP-4 consumes tenant scope to orchestrate/control state within the boundary
       +-> SP-8 consumes tenant scope to validate and process instance requests
```

### Acceptance-time flow

1. Approve the normative tenant model (`tenant = customer/client`, `tenant_id` canonical).
2. Prove project is the only normative subordinate scope in v1.
3. Prove operational classifications stay non-authoritative.
4. Prove ownership composition keeps `created` / `adopted` / `external` intact.
5. Prove quota authority is defined once here and downstream documents are positioned as consumers.
6. Record `AC-CAP-TENANCY-READY` evidence only after the above are visible in accepted artifacts.

## File Plan

| File | Action | Description |
|---|---|---|
| `openspec/changes/CAP-TENANCY/proposal.md` | Existing input | Source intent and scope guardrails for the design. |
| `openspec/changes/CAP-TENANCY/specs/tenancy-contract/spec.md` | Existing input | Normative requirements the design must operationalize. |
| `openspec/changes/CAP-TENANCY/design.md` | Create | Persist this contract-first design and handoff model. |
| `docs/specs/platform/portfolio.json` | Modify later | Record dependency/readiness alignment for `CAP-TENANCY` and downstream consumers after approval/verification. |
| `docs/specs/platform/SP-3-remote-backend-providers.md` | Modify later | Replace any tenancy-definition language with explicit consumption of `CAP-TENANCY`. |
| `docs/specs/platform/SP-4-control-plane-core.md` | Modify later | Treat tenancy as an input contract rather than a control-plane-owned model. |
| `docs/specs/platform/SP-8-instance-lifecycle-requests.md` | Modify later | Remove quota/tenant redefinition and consume `CAP-TENANCY` vocabulary instead. |

## Acceptance Strategy

`CAP-TENANCY` is ready when `AC-CAP-TENANCY-READY` can be verified from accepted artifacts without relying on provider/runtime implementation.

| Evidence target | Proof |
|---|---|
| Canonical tenant unit | Proposal/spec/design all state tenant = customer/client and `tenant_id` as canonical technical identifier. |
| Subordinate scope | Artifacts state project is the only normative subordinate scope in v1 and cannot stand alone. |
| Operational-class boundary | Artifacts state `PROD`/`QA`/`DEV` consume tenant scope and reject `environment_family` as a v1 tenancy concept. |
| Isolation boundary | Design states tenant is the minimum isolation boundary and keeps enforcement provider-neutral. |
| Ownership composition | Artifacts preserve `created` / `adopted` / `external` semantics while binding them to tenant scope. |
| Single quota authority | CAP-TENANCY artifacts define quota once; SP-3/SP-4/SP-8 are documented as consumers only. |
| Downstream readiness | Portfolio and downstream specs reference CAP-TENANCY as prerequisite input instead of redefining tenancy/quota semantics. |

## Implementation / Decomposition Guidance

1. **Finish the prerequisite contract first**
   - Keep all work in OpenSpec/spec/portfolio artifacts.
   - Do not introduce auth, persistence, or provider runtime structures in this change.

2. **Align downstream documents next**
   - Update SP-3 to say adapters enforce isolation for a tenant model defined by `CAP-TENANCY`.
   - Update SP-4 to consume tenant/project/quota inputs without becoming their authority.
   - Update SP-8 to consume quota and tenant scope rather than define “per role or per client” limits itself.

3. **Only then let implementation slices consume the contract**
   - Provider/runtime slices may add tenant-aware enforcement.
   - Control-plane slices may add tenant-aware persistence or APIs.
   - Request slices may add tenant-scoped validation.
   - None of those slices may reopen the core semantic decisions above.

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Consumer drift | SP-3/SP-4/SP-8 may continue to carry their own tenancy language | Make consumer responsibilities explicit in the handoff matrix and align downstream docs before implementation. |
| Boundary bleed into control plane or auth | This would turn a prerequisite contract into a much larger architecture change | Keep this design documentation-only and forbid persistence/auth/provider runtime design here. |
| Quota ambiguity | Later work could claim local quota authority | State attachment/evaluation authority once here and treat all later quota logic as consumption. |
| Under-specified handoff | Consumers may infer fields differently | Use the conceptual input contract as the required minimum handoff shape. |

## Rollout

No runtime migration is required. This change establishes planning authority only.

Rollout order:
1. Approve proposal/spec/design.
2. Align portfolio + downstream spec references.
3. Break consumer implementation into later changes that explicitly depend on `CAP-TENANCY`.

## Open Questions

None.
