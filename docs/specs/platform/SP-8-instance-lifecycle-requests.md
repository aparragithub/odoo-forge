# SP-8 — Instance lifecycle requests

**Layer:** Experience · **Status:** planned · **SDD change name (proposed):** `platform-instance-lifecycle-requests`

## Purpose
This sub-project delivers the **instance-request journey** for control-plane users (§4 actor 3):
requesting a new **PROD** instance, a **QA instance generated from a given PROD**, or a **randomized
DEV** instance for general flow testing. It is the request-intake and fulfillment orchestration that
turns a role-authorized request into a provisioned, registered instance on a real target.

It builds no new external-concern port; it **composes** the ports and orchestration already built.

## Actor(s) served
**Control-plane users** with roles (functional / devops / customer / CTO) (§4 actor 3). Unblocks:
"Request a new PROD instance, a QA instance generated from a given PROD, or a randomized DEV instance."

## Port & adapters
Orchestration only — no new port. It composes:
- **`DatabaseProvider`** (SP-2) — provision (PROD), clone prod→QA (QA), or randomize (DEV).
- **`BackendProvider`** (Slice 4b + SP-3) — deploy the instance to the chosen target.
- **SP-4** control-plane API + registry — record the request outcome and instance pointers.
- **SP-5** RBAC — authorize the request by role before fulfillment.

## What it reuses (does NOT build)
- SP-2 lifecycle verbs (provision / clone / randomize) — this sub-project *chooses which* per request
  type, it does not reimplement them.
- SP-3/4b backends for placement.
- SP-4 registry for state; SP-5 for authorization.
- SP-1 image publish/pull when a request maps to a pre-built server instance (Model B).

## Pointers, not copies
Each fulfilled request adds a registry entry with the **image digest** (server instance) or
**repo ref**, the **DB connection ref**, and the target coordinates — plus **lineage** (which PROD a
QA was cloned from). No instance data stored centrally (§Principle 4).

## Scope
- Request intake for three instance types: **PROD**, **QA-from-PROD**, **randomized-DEV**.
- Map each type to the correct DB lifecycle op (SP-2) + backend placement (SP-3/4b).
- Enforce role authorization (SP-5) at request time.
- Register the resulting instance and its pointers/lineage in SP-4.

## Non-goals
- No new port or adapter.
- No DB lifecycle implementation (SP-2) or backend adapter (SP-3) — composition only.
- No CI/CD execution (SP-6), though a PROD request may hand off to it.
- No web UI (SP-9) — this is the request/fulfillment flow; UI is layered separately.

## Dependencies
Upstream: **SP-2** (DB lifecycle), **SP-3** (targets), **SP-4** (registry/API), **SP-5** (RBAC),
**SP-10** (PROD gating/guardrails + append-only audit for PROD requests)
(§6, §7). Ordered after SP-7 in the experience layer.

## Success criteria
- Each request type produces the correct outcome: PROD → provisioned DB + deployed instance;
  QA → cloned-from-named-PROD DB + deployed instance (lineage recorded); DEV → randomized DB +
  deployed instance. Verified end to end.
- Unauthorized roles are rejected before any provisioning occurs (authorization test).
- Every fulfilled request yields exactly one canonical registry entry (anti-drift, §Principle 5).
- Orchestration is pure and import-linter-clean; all external work via existing adapters. Strict TDD.

## Open decisions
- Approval workflow: are requests auto-fulfilled or is there a human approval step (esp. PROD)?
  PROD requests are gated by **SP-10** guardrails/gated promotions and recorded in its append-only
  audit trail; this decision resolves the human-approval step against that mechanism.
- Which roles may request which instance types (overlaps SP-5 permission granularity).
- QA-from-PROD anonymization: QA is **anonymized by default** (overlaps SP-2 PII rules); serving
  real PROD data to QA requires explicit, audited authorization rather than being the default.
- Quotas/limits per role or per client.
