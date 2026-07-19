# Proposal: CAP-RESOURCE-OWNERSHIP

## Intent

Define `CAP-RESOURCE-OWNERSHIP` ("Resource Ownership") as the contract-first platform capability that establishes one provider-neutral answer to "who owns a managed resource, on what evidence, and under whose tenant." Today ownership exists only as a local, single-adapter concept: the `ResourceOwnership` enum and value types in `src/odoo_forge/database/types.py` are database-scoped, and the real enforcement (`LocalOwnershipAuthority`, `provider.py`) is Docker-label-specific and adapter-private. This capability generalizes the vocabulary from database-domain-scoped to platform-capability-scoped and introduces a `PORT-RESOURCE-OWNERSHIP` port in the core, without reimplementing or relocating the existing Docker enforcement.

The outcome is a stable ownership/attribution contract — ownership state, receipt/evidence shape, tenant attribution, and composition with `CAP-TENANCY` and `CAP-DURABLE-OPERATIONS` — sufficient to satisfy the currently-empty readiness gate `AC-CAP-RESOURCE-OWNERSHIP-READY` (gap `G0`) and unblock its four downstream hard-edges: `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY`.

## Scope

### In Scope
- Define a normative, provider-neutral **resource-ownership state model** that generalizes the existing `created` / `adopted` / `external` vocabulary from the database domain to arbitrary resource kinds (databases, backend containers, image registry entries, future remote/K8s targets) — aligning with, not replacing, `src/odoo_forge/database/types.py`.
- Define the **ownership receipt / evidence shape**: what proof a resource kind must carry to claim ownership (opaque operation proof, owned resource ids, live-proof expectation), generalized from `CreationReceipt` without baking in Docker-label semantics.
- Define **tenant attribution**: how an owned resource links to a tenant boundary as defined by `CAP-TENANCY`, composing with (not replacing) `created` / `adopted` / `external`.
- Define **composition with `CAP-DURABLE-OPERATIONS`**: reuse its operation-identity model for evidence/receipts rather than duplicating it.
- Introduce a provider-neutral **`PORT-RESOURCE-OWNERSHIP`** port surface in `src/odoo_forge/ports/` that expresses the ownership contract independent of any persistence/custody adapter.
- Define acceptance evidence for the readiness gate `AC-CAP-RESOURCE-OWNERSHIP-READY` sufficient to unblock the four downstream items to spec/design.

### Out of Scope (Non-Goals)
- **No control-plane authority service** — "who queries/answers ownership at runtime" belongs to `SP-CONTROL-PLANE-AUTHORITY`.
- **No lifecycle reclamation / retention policy** — orphan reclamation, garbage collection, and retention belong to `SP-RESOURCE-LIFECYCLE`.
- **No coordinated data-copy or environment-request workflow logic** — those belong to `WF-DATA-COPY` and `WF-ENVIRONMENT-REQUEST`.
- **No duplication of `CAP-DURABLE-OPERATIONS`' operation-identity model** — compose with it.
- **No rewrite or relocation** of the existing Docker `LocalOwnershipAuthority` / `provider.py` enforcement; it stays as proof-of-pattern for a future first adapter.
- **No merging** of this capability into an umbrella foundation change with `CAP-TENANCY` / `CAP-DURABLE-OPERATIONS` (forbidden by portfolio decision `DG`).

## Capabilities

### New Capabilities
- `resource-ownership-contract`: normative, provider-neutral definition of ownership state, receipt/evidence shape, tenant attribution, durable-operation composition, and the `PORT-RESOURCE-OWNERSHIP` surface.

### Modified Capabilities
- None. Downstream changes adopt this contract in their own slices; the existing Docker adapter is aligned only at spec-language level, not rewritten here.

## Approach

Use a contract-first proposal, matching the accepted `CAP-TENANCY` and `CAP-DURABLE-OPERATIONS` precedent. Establish one canonical ownership contract before any control-plane, lifecycle, or workflow change extends ownership into runtime behavior.

The generalization is deliberately additive: the existing `ResourceOwnership` enum and value types remain the anchor, and the capability lifts their vocabulary to platform scope rather than introducing a competing model. `PORT-RESOURCE-OWNERSHIP` expresses the contract as a port so the eventual authority service (`SP-CONTROL-PLANE-AUTHORITY`) and the existing Docker `LocalOwnershipAuthority` become adapters/consumers of a shared surface — but adapter selection and custody-ledger implementation are explicitly deferred.

This proposal stays narrow: it creates the prerequisite contract and its readiness gate, not the authority service, not retention policy, and not workflow logic. Ownership state, evidence, and tenant attribution are authored exactly once here; downstream changes may query or enforce them, but may not redefine them.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/changes/CAP-RESOURCE-OWNERSHIP/` | Modified | Proposal and follow-on spec/design/tasks for the ownership capability |
| `openspec/specs/` | New | Canonical capability spec for the resource-ownership contract and readiness gate |
| `src/odoo_forge/ports/` | New (follow-up) | Home of the provider-neutral `PORT-RESOURCE-OWNERSHIP` surface |
| `src/odoo_forge/database/types.py` | Align only | Existing `ResourceOwnership` / `DatabaseRef` / `CreationReceipt` vocabulary to generalize from, not replace |
| `src/odoo_forge_postgres_docker/authority.py`, `provider.py` | Proof-of-pattern | First-adapter reference; out of scope to rewrite in this change |
| `docs/specs/platform/portfolio.json` | Modified | Populate `AC-CAP-RESOURCE-OWNERSHIP-READY` evidence and confirm downstream dependency edges |
| `docs/specs/2026-07-14-stabilization-roadmap.md` | Follow-up alignment | Authoritative intent and dependency edges |
| `docs/13-src-ports-map.md`, `docs/03-src-core-map.md` | Follow-up alignment | Update placement docs once the port exists |
| `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, `WF-DATA-COPY` | Follow-up alignment | Must consume this ownership contract rather than redefine ownership/attribution |

## Readiness Gate — `AC-CAP-RESOURCE-OWNERSHIP-READY`

The gate is currently empty (gap `G0`). This capability closes it by producing acceptance evidence that the four downstream hard-edges can consume without inventing their own ownership rules:

- A normative ownership state model generalized from `created` / `adopted` / `external`, provider-neutral and resource-kind-agnostic.
- A receipt/evidence shape that any resource kind can satisfy, free of Docker-label specifics.
- Explicit tenant-attribution composition with `CAP-TENANCY` and operation-identity composition with `CAP-DURABLE-OPERATIONS`.
- A defined `PORT-RESOURCE-OWNERSHIP` surface that a future authority service and the existing Docker authority can both implement/consume.
- Explicit handoff statements positioning `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY` as consumers.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope bleed into `SP-CONTROL-PLANE-AUTHORITY` (a full ownership *service* vs. a *contract*) | High | Keep this capability contract-only; defer "who queries/answers ownership" runtime authority to that change |
| Duplicating `CAP-DURABLE-OPERATIONS`' operation-identity model | Med | Require composition with its existing identity/receipt model; do not re-author operation identity |
| Provider leakage — Docker-label semantics baked into the "neutral" contract | Med | Derive vocabulary from core value types only; keep label/live-proof mechanics as adapter concerns |
| Ownership/tenancy conflation with `CAP-TENANCY`'s boundary | Med | Define tenant attribution as composition with, not replacement of, ownership state |
| Scope bleed into `SP-RESOURCE-LIFECYCLE` retention/reclamation policy | Med | Explicitly exclude retention, GC, and orphan reclamation as downstream lifecycle work |
| Folding into an umbrella foundation change (forbidden by `DG`) | Low | Keep this an independent roadmap enabler with its own gate |
| Thin pre-existing spec language (no SP-style stub yet) | Med | Anchor to `portfolio.json`, the stabilization roadmap, and transfers `X20`–`X23` reclassification |

## Rollback Plan

Revert the `CAP-RESOURCE-OWNERSHIP` proposal/spec artifacts and keep `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY` blocked from ownership-dependent design until a corrected contract is approved. No runtime rollback is needed: this proposal introduces planning authority, not product behavior. The existing Docker `LocalOwnershipAuthority` / `provider.py` remains untouched, so current adapter behavior is unaffected either way.

## Dependencies

- `openspec/changes/CAP-RESOURCE-OWNERSHIP/exploration.md`
- `docs/specs/2026-07-14-stabilization-roadmap.md`
- `docs/specs/platform/portfolio.json`
- `src/odoo_forge/database/types.py`
- `src/odoo_forge_postgres_docker/authority.py`, `src/odoo_forge_postgres_docker/provider.py`
- `docs/13-src-ports-map.md`, `docs/03-src-core-map.md`
- Accepted precedents: `CAP-TENANCY`, `CAP-DURABLE-OPERATIONS`

## Success Criteria

- [ ] The accepted contract generalizes ownership state from database-scoped `created` / `adopted` / `external` to a provider-neutral, resource-kind-agnostic model without replacing the existing enum/value types.
- [ ] The contract defines a receipt/evidence shape reusable by any resource kind, free of Docker-label specifics.
- [ ] Tenant attribution is defined as composition with `CAP-TENANCY`, and operation identity is defined as composition with `CAP-DURABLE-OPERATIONS` (no duplication).
- [ ] A `PORT-RESOURCE-OWNERSHIP` surface is defined that both a future authority service and the existing Docker authority can implement/consume.
- [ ] `AC-CAP-RESOURCE-OWNERSHIP-READY` evidence is sufficient to unblock `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY` to spec/design.
- [ ] The change stays independent of the CAP-TENANCY / CAP-DURABLE-OPERATIONS umbrella (honoring decision `DG`) and does not rewrite the existing Docker enforcement.

## Proposal Question Round

These questions are meant to sharpen the contract before it is finalized — surfacing business rules, composition boundaries, and product tradeoffs. Answer, skip, correct the framing, or request a second round.

1. Should the ownership state model add any new states beyond generalizing `created` / `adopted` / `external` (for example, a `reserved`/`pending` state that the Docker authority's reserve/bind/activate/retire lifecycle already implies), or must v1 stay to the existing three to avoid over-modeling?
2. For tenant attribution, is a resource required to always carry a tenant link at ownership time, or are pre-tenancy / `external` resources allowed to be tenant-unattributed until adopted?
3. Should `PORT-RESOURCE-OWNERSHIP` in v1 express only read/attest semantics (state + evidence shape), or also the write/transition verbs (reserve, bind, activate, retire, adopt) — knowing the latter risks bleeding toward `SP-CONTROL-PLANE-AUTHORITY`?
4. How much of the receipt "live-proof" expectation should be normative here versus left to each adapter, so the contract stays provider-neutral but still forces ownership to be verifiable?

Resolved decisions (confirmed by the user — binding on spec and design):
- **States:** v1 keeps exactly `created` / `adopted` / `external`, generalized to platform scope; no new states (no `reserved`/`pending`).
- **Tenant attribution:** composes with ownership; `external` (and pre-tenancy) resources may remain tenant-unattributed until adopted — a tenant link is not mandatory at ownership time.
- **Port surface:** `PORT-RESOURCE-OWNERSHIP` v1 expresses ownership state + evidence/attestation (read/attest) shape only; transition verbs (reserve/bind/activate/retire/adopt) are described but their runtime authority is deferred to `SP-CONTROL-PLANE-AUTHORITY`.
- **Live-proof:** the receipt requires verifiable ownership (opaque operation proof + owned resource ids + a live-proof expectation), but the concrete live-proof mechanism stays an adapter concern — not normative in this contract.
- **Docker enforcement:** the existing `LocalOwnershipAuthority` / `provider.py` remains untouched and becomes a reference adapter later.
