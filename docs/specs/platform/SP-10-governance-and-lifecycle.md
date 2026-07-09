# SP-10 — Governance & lifecycle

**Layer:** Orchestration · **Status:** planned · **SDD change name (proposed):** `platform-governance-and-lifecycle`

## Purpose
This sub-project adds the **governance and lifecycle** layer over the control plane: the
append-only **audit trail**, **PROD guardrails** with gated promotions, **GC/retention** for the
resources the platform creates, and **backup orchestration** with verified restore drills. It is
the mechanism that keeps a growing, multi-actor platform accountable (who did what, especially to
PROD) and bounded (no unbounded growth, no silent data loss).

It grounds the founding "reuse later (when the control plane exists)" items into a concrete
sub-project: backup service (design line 185) and governance — `policies.yaml`, append-only audit
trail, PROD instance guardrails, gated promotions (design line 186).

## Actor(s) served
**Control-plane users** and **DevOps** exercising governance over PROD (§4 actors 2 and 3): they
get an auditable record of requests/approvals and enforced guardrails before PROD changes. It also
protects **all** actors indirectly by preventing unbounded growth (orphaned clones/instances/image
digests) and data loss (unverified backups).

## Port & adapters
This sub-project **orchestrates** rather than adding an external-concern port. It reuses
cloud-native scheduling/retention where available and stores its records in an **append-only
store** adjacent to SP-4's canonical instance registry. Where a target offers native lifecycle
policies (e.g. object-store retention, RDS snapshot retention), the orchestration drives them
instead of reimplementing them.

## What it reuses (does NOT build)
- **SP-2** dump/restore + anonymization **primitives** — SP-10 schedules, retains, and
  restore-drill-verifies them; it does not reimplement DB operations.
- **SP-1** image publish/pull and **SP-3** instance placement — SP-10 reclaims their orphans; it
  does not build registries or backends.
- **SP-4** registry/persistence as the substrate its append-only audit store sits beside.
- Cloud-native **scheduling / retention** (cron, object-store lifecycle, snapshot retention).

## Pointers, not copies
The audit trail and lifecycle records store **references and events** (who/what/when, image
digests, DB/instance refs, TTL/expiry, backup-artifact refs), never instance data, image layers,
or DB contents (§Principle 4). Backups themselves live in the DB/object-store provider; SP-10
records and verifies their references.

## Scope
- **Append-only audit trail**: who requested/approved what — especially PROD changes — as an
  immutable, queryable record.
- **PROD guardrails + gated promotions** (design line 186): PROD-affecting actions require an
  approval gate before fulfillment; promotions are gated, not implicit.
- **GC / retention**: TTL for DEV/QA DB clones and instances, image-digest retention policy, and
  orphan reclamation (resources with no live registry entry).
- **Backup orchestration + restore drills** (design line 185): schedule backups over SP-2's
  dump/restore primitive, enforce retention, and periodically verify restores succeed.

## Non-goals
- No new external-concern port or adapter.
- No DB/image/backend **implementation** — it composes SP-1/SP-2/SP-3 primitives (SP-2 owns
  dump/restore + anonymization; SP-10 only schedules/retains/verifies them).
- No RBAC engine (SP-5) — it consumes role decisions; it does not define roles.
- No web UI (SP-9) — the panel surfaces SP-10 state; SP-10 owns the logic.

## Dependencies
Upstream: **SP-4** (registry/persistence) and the ports it reclaims — **SP-1** (images),
**SP-2** (DBs), **SP-3** (instances). Ordered after SP-6, feeding SP-7/SP-8/SP-9 (§7).

## Success criteria
- DEV/QA clones and instances **auto-expire by TTL**; expiry is enforced, not advisory.
- PROD changes are recorded in the **append-only** audit trail and cannot bypass the guardrail
  gate (verified by test).
- A **restore drill** verifies a backup can be restored end to end.
- No orphaned image digests or DB copies accumulate under normal use (reclamation verified).
- Governance/lifecycle logic stays pure and import-linter-clean; scheduling/retention runs at the
  adapter/edge. Strict TDD.

## Open decisions
- Append-only store shape — same PostgreSQL as SP-4 (separate append-only tables) vs. a dedicated
  log store.
- Default TTLs per environment (DEV/QA) and per resource type, and who may override them.
- Which promotions require a human gate vs. policy-automated approval.
- Backup cadence/retention defaults and where restore-drill targets run.
