# Exploration: CAP-RESOURCE-OWNERSHIP

> Artifact store: openspec (primary). Secondary record: Engram `sdd/CAP-RESOURCE-OWNERSHIP/explore` (id 9629).
> Phase: exploration only — no proposal, no implementation.

## Intent

`CAP-RESOURCE-OWNERSHIP` ("Resource Ownership") is the next platform enabler per
`docs/specs/2026-07-14-stabilization-roadmap.md`. In `docs/specs/platform/portfolio.json`
it is a `prerequisite` capability, `status: proposed`, `owner_role: Runtime`, gated by
`AC-CAP-RESOURCE-OWNERSHIP-READY` (empty evidence, gap `G0`). It is a **ready leaf**: no
unmet prerequisites, and it HARD-blocks four downstream items via its readiness handoff —
`SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and
`WF-DATA-COPY`.

## Current State

Resource ownership already exists in code, but only as a **local, single-adapter concept**,
not a platform capability:

- `src/odoo_forge/database/types.py:24` — `ResourceOwnership` StrEnum (`CREATED`, `ADOPTED`,
  `EXTERNAL`), plus `DatabaseRef`, `OperationIdentity`, `CreationReceipt`. Core,
  provider-neutral value types, but scoped only to the database domain.
- `src/odoo_forge_postgres_docker/provider.py` — the real enforcement logic
  (`assert_live_ownership`, `verify_runtime_ownership`, label-based live-proof,
  receipt-scoped delete/cleanup/reconcile with rollback). Adapter-private and
  Docker-label-specific.
- `src/odoo_forge_postgres_docker/authority.py` — `LocalOwnershipAuthority`: a working
  Ed25519-signed, fsynced local-JSON custody ledger with reserve/bind/activate/retire
  states and short-lived signed evidence. A proven ownership-authority pattern, but
  adapter-local filesystem state, not tenant-aware, and not reusable by other resource
  kinds (backend containers, image registry, future remote/K8s targets).
- No `PORT-RESOURCE-OWNERSHIP` (or equivalent) exists in `src/odoo_forge/ports/`
  (confirmed against `docs/13-src-ports-map.md`).
- No dedicated `docs/specs/platform/CAP-RESOURCE-OWNERSHIP*.md` spec stub exists — only
  `portfolio.json` and the stabilization roadmap define intent.

### Portfolio evidence

Transfers `X20`–`X23` show adoption, deletion-authorization, and orphan-detection scopes
were explicitly **reclassified out of** the historical `SP-2` (database provider) **into
this capability** — those semantics are meant to become capability-level, not
provider-specific. Related achieved capabilities already anticipated this gap:

- `CAP-TENANCY`'s design states tenant authority "composes with `created`/`adopted`/`external`;
  it does not replace them" — that composition is currently **undefined**.
- `CAP-DURABLE-OPERATIONS` already owns workflow-level operation identity/checkpoints/
  terminal-commit; resource-ownership must **compose with, not duplicate**, that identity model.
- Decision `DG` ("independent roadmap enablers") **forbids** merging this into an umbrella
  foundation change with CAP-TENANCY / CAP-DURABLE-OPERATIONS.

## Affected Areas

- `src/odoo_forge/database/types.py` — existing ownership vocabulary to align with, not replace.
- `src/odoo_forge/ports/` — where a new provider-neutral ownership port would live.
- `src/odoo_forge_postgres_docker/authority.py`, `provider.py` — proof-of-pattern for a first
  adapter, but **out of scope to rewrite** in this change.
- `docs/specs/platform/portfolio.json`, `docs/specs/2026-07-14-stabilization-roadmap.md` —
  authoritative intent and dependency edges.
- `docs/13-src-ports-map.md`, `docs/03-src-core-map.md` — architecture placement docs to update
  once the port exists.
- Downstream (**NOT** implemented here): `openspec/changes/sp-data-environments/` and future
  `WF-DATA-COPY`, `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`.

## Approaches

### 1. Contract-first capability (recommended)
Define a provider-neutral ownership/attribution contract (state, receipt, tenant linkage,
operation-identity composition) plus a readiness gate, without reimplementing or relocating
the existing Docker authority.
- **Pros:** matches the CAP-TENANCY / CAP-DURABLE-OPERATIONS precedent; unblocks 4 downstream
  items without premature coupling; keeps the change reviewable.
- **Cons:** requires discipline not to silently absorb `SP-CONTROL-PLANE-AUTHORITY`'s "who
  queries ownership" concern or `SP-RESOURCE-LIFECYCLE`'s retention policy.
- **Effort:** Medium.

### 2. Generalize the existing Docker authority into a shared port immediately
Extract `LocalOwnershipAuthority` into a reusable adapter now.
- **Pros:** concrete, testable quickly.
- **Cons:** prematurely couples the contract to one persistence/custody implementation while
  `SP-CONTROL-PLANE-AUTHORITY` (the eventual authority service) is still unresolved; risks the
  same "provider-shaped contract" mistake CAP-TENANCY explicitly avoided.
- **Effort:** High.

### 3. Let each downstream consumer define its own ownership rules (status quo)
- **Pros:** none beyond short-term speed.
- **Cons:** contradicts the portfolio's reclassification of adoption/deletion/orphan scopes
  into this single capability; guarantees drift across 4 dependents.
- **Effort:** High rework risk.

## Recommendation

**Approach 1.** Frame `CAP-RESOURCE-OWNERSHIP` as the capability that defines resource
ownership state, receipt/evidence shape, tenant attribution, and composition with
`CAP-TENANCY` and `CAP-DURABLE-OPERATIONS` — **contract only**, deferring the control-plane
authority service, lifecycle reclamation policy, and workflow-specific logic to their
respective downstream changes.

## Risks & Scope Boundaries

- Scope bleed into `SP-CONTROL-PLANE-AUTHORITY` (a full ownership *service* vs. a *contract*).
- Duplicating `CAP-DURABLE-OPERATIONS`' operation-identity model instead of composing with it.
- Provider leakage: baking Docker-label semantics into the "neutral" contract.
- Ownership/tenancy conflation with `CAP-TENANCY`'s boundary.
- `DG` decision forbids folding this into an umbrella foundation change.
- No dedicated spec stub exists yet (unlike SP-1..SP-10), so there is less pre-existing spec
  language to anchor the proposal against than CAP-TENANCY had.

## Ready for Proposal

Yes — same contract-first framing as `CAP-TENANCY` / `CAP-DURABLE-OPERATIONS`.
