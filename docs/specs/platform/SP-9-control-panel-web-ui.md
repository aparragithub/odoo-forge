# SP-9 — Control panel (web UI)

> **Historical brief (superseded).** Preserved for SP-era design lineage. Use
> [`portfolio.json`](portfolio.json) for current status, evidence, dependencies, and handoffs.

**Layer:** Experience · **Status:** planned · **SDD change name (proposed):** `platform-control-panel-web-ui`

## Purpose
This sub-project delivers the **operational control panel** — the web UI that DevOps, functional, and
CTO users operate to **view instances per server, decide on updates, and issue requests** (§4 actors 2
and 3). It is a thin presentation surface over the **SP-4 API** and is gated by **SP-5 RBAC**: what a
user sees and can do is entirely determined by their role. It adds no business logic and no
external-concern port — every action is an SP-4 API call, every permission an SP-5 decision.

This is the human face of the "conductor" (§1): the panel makes visible the canonical instance
registry and the lifecycle actions the orchestration layer already exposes.

## Actor(s) served
**DevOps (operations)** (§4 actor 2) — "views a control panel of instances per server → decides to
apply an update". Also **control-plane users** (functional / CTO) (§4 actor 3) for viewing state and
issuing requests. Unblocks: "the panel devops/functional/CTO operate" (§6 SP-9).

## Port & adapters
No new external-concern port. It consumes:
- **SP-4** control-plane API — instance listing, state, and lifecycle actions.
- **SP-5** RBAC — role-aware rendering and per-action authorization; login via the reused OIDC/SSO flow.
It orchestrates SP-8 (issue requests) and surfaces SP-6 status (update/deploy progress) through the API.

## What it reuses (does NOT build)
- SP-4's API as the **only** data/action source — the UI holds no independent state or business rules.
- SP-5's OIDC login and role model — no separate auth in the UI.
- SP-6/SP-8 flows for actions the panel triggers (apply update, request instance).

## Pointers, not copies
The UI is stateless with respect to platform data: it renders what SP-4 returns (pointers: digests,
DB refs, target coordinates, instance state) and stores nothing itself beyond ephemeral session/UI
state (§Principle 4).

## Scope
- Instance dashboard: instances per server/target, their state, and stored pointers.
- Role-aware views and actions (SP-5): apply update (→ SP-6), issue request (→ SP-8), inspect status.
- OIDC login through the SP-5 flow.
- Read-through to SP-6 pipeline/deploy status and SP-8 request outcomes.

## Non-goals
- No business logic, no direct adapter calls — everything goes through the SP-4 API.
- No auth of its own (delegated to SP-5).
- No new ports; no instance provisioning logic (SP-8 owns fulfillment).
- Not an Odoo-instance admin UI (Odoo owns its own back office).

## Dependencies
Upstream: **SP-4** (API/registry) and **SP-5** (RBAC) (§6, §7). Consumes SP-6 (status) and SP-8
(requests). Last in the build order — it composes everything below it.

## Success criteria
- The panel lists instances with their canonical registry state and pointers, sourced only from SP-4.
- Role gating is enforced in both rendering and action authorization (a customer/functional user
  cannot trigger devops-only actions) — verified against SP-5.
- Triggering an update/request from the UI results in the correct SP-6/SP-8 flow, with status
  reflected back. No platform state is duplicated in the UI (anti-drift, §Principle 5).
- UI/edge code stays outside the pure core; the purity gate and import-linter stay green. Strict TDD
  for any non-trivial view/controller logic.

## Open decisions
- UI stack/framework — reconcile with the control-plane transport/persistence choice (§8, design line 228).
- Server-rendered vs. SPA against the SP-4 API.
- How much SP-6 pipeline detail to surface vs. deep-link into the CI engine's native UI.
- Real-time updates (polling vs. push) for instance/pipeline state.
