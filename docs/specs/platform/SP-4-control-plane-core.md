# SP-4 — Control plane core

**Layer:** Orchestration · **Status:** planned · **SDD change name (proposed):** `platform-control-plane-core`

## Purpose
This sub-project builds the **control plane** itself — `forge server`, the "conductor, not the
orchestra" (§1). It delivers three things: an **API**, the **canonical instance registry** (the
platform's single source of truth for *which instance runs where*), and the **composition root**
that selects **one adapter per port at init** (§Principle 3). It is the first Layer 2 sub-project
and the point where the ports built in SP-1/2/3 are wired into a running orchestrator.

The server remains thin by design: it stores **pointers** (repo URLs, image digests, DB connection
refs) plus the instance registry, and delegates every external concern to a chosen adapter. It is
not a data lake (§Principle 4).

> **Scope note:** the "one adapter per port at init" statements below describe the
> foundation/CLI composition root as it exists today. Whether the control plane itself binds
> one adapter per port globally, or selects an adapter **per instance** from a registered set,
> is an **open decision** (roadmap §8, "Principle 3 scope") — not yet settled. Read this brief's
> success criteria as scoped to the current foundation/CLI composition root, not as a
> resolution of that open decision.

## Actor(s) served
Indirectly all three actors (§4) — it is the substrate every journey composes on top of. Directly,
it serves **DevOps** by exposing instance state for the control panel (SP-9) and by being the API
the experience layer (SP-7/8) calls. No end-user journey ships here; those are Layer 3.

## Port & adapters
This sub-project **orchestrates** the existing ports rather than adding one. It houses the
**composition root** that binds exactly one adapter per concern at initialization:

- `SourceProvider` → git (Slice 2b)
- `ImageRegistryProvider` → SP-1's chosen adapter
- `DatabaseProvider` → SP-2's chosen adapter
- `BackendProvider` → local docker (4b) or SP-3's chosen remote adapter

Concerns are **not** mixed across providers at runtime (§Principle 3) — the same anti-drift
discipline as the single canonical lockfile.

## What it reuses (does NOT build)
- All four ports and their adapters (SP-1/2/3 + foundation) — the server calls them, never
  reimplements their concerns.
- The **pointer-only** model already proven by `project.lock`.
- An existing **API framework** and **persistence engine** for the registry — grounded in the
  founding **Phase-4 PostgreSQL control plane** (design line 228: "real server-side state"),
  not invented from scratch.

## Pointers, not copies
The canonical instance registry stores: instance identity, the repo URL + resolved SHA, the image
**digest**, the **DB connection ref**, and the target coordinates (which backend). It stores no
source, no image layers, no DB contents (§Principle 4).

## Scope
- HTTP/RPC **API** surface for instance CRUD + state queries (consumed by SP-5/7/8/9).
- **Canonical instance registry** persistence with strict FK discipline — one place, no duplicated
  DDL (§Principle 5; the `odoo-idp` dual-DDL / `mer-fk-refactor` scar).
- **Composition root** selecting one adapter per port at init.
- Ground persistence in the founding **Phase-4 PostgreSQL control plane** (design line 228) and
  confirm this does **not** violate the Phase-2-CLI-scoped "no database" note (design line 227).
- **Registry ↔ backend reconciliation.** The stored instance registry must **reconcile against
  backend introspection** — founding line 227: "ask the backend — never a parallel registry file
  that can drift". Define a periodic and on-read reconciliation so an instance killed out-of-band does
  not leave the registry asserting it still runs.
- **Tenancy contract consumption.** Consume `CAP-TENANCY` as the sole source for the
  customer/client `tenant_id`, child-only project scope, operational classifications, minimum
  isolation expectations, ownership composition, and quota authority. The control plane may
  orchestrate and record these inputs, but it does not define tenancy, isolation, or quotas.
- **Secret-manager references.** Resolve secret-manager **refs** at composition and pass **refs
  only** (never plaintext) into the backend plan/env; the adapter resolves them target-side.

## Non-goals
- No auth/RBAC (SP-5).
- No CI/CD triggering (SP-6).
- No actor-facing journeys or UI (SP-7/8/9).
- No new external-concern port.

## Dependencies
Upstream: **CAP-TENANCY** (`AC-CAP-TENANCY-READY`) for tenant identity, project
subordination, isolation, ownership, and quota inputs; **SP-1, SP-2, SP-3** (§6 — "the control
plane only pays off once it has ports to orchestrate", §7); plus the git `SourceProvider`
foundation. Downstream: SP-5, SP-6, SP-7, SP-8, SP-9.

## Success criteria
- One adapter per port is bound at init for the composition root as scoped today; a runtime
  attempt to mix adapters within that scope is impossible by construction
  (composition-root-enforced). This does **not** presuppose the outcome of the open
  per-instance-adapter-selection decision (§8 "Principle 3 scope") — if that decision expands
  Principle 3 to per-instance selection, this criterion is revisited accordingly.
- The instance registry is the **single** canonical store — no duplicated DDL; FK discipline
  verified (anti-drift regression guard).
- API round-trips: register an instance, query it, and read back the exact pointers stored.
- Core/domain logic stays pure and import-linter-clean; API framework and persistence live in an
  adapter/edge layer, never imported by `odoo_forge` core. Strict TDD throughout.

## Open decisions
- **Control plane transport/stack** — API framework and persistence engine for the instance registry,
  grounded in the founding **Phase-4 PostgreSQL control plane** (§8, design line 228).
- Registry schema shape and migration story (must respect single-canonical / anti-drift).
- Whether the composition-root config is file-based, env-based, or API-driven.
