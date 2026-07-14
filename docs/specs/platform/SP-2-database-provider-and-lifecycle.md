# SP-2 — DatabaseProvider + DB lifecycle

> **Historical brief (superseded).** Preserved for SP-era design lineage. The current portfolio
> separates the accepted `DatabaseProvider` contract from the still-absent concrete adapter and
> managed data workflows. Use [`portfolio.json`](portfolio.json) as authority.

**Layer:** Ports & adapters · **Status:** planned · **SDD change name (proposed):** `platform-database-provider`

## Purpose
This sub-project introduces the `DatabaseProvider` port and the **database lifecycle** operations
that sit on top of it. It turns the dockerized Postgres already shipped in Slice 4b into a
pluggable concern with interchangeable adapters, and adds the lifecycle verbs the platform needs:
**provision**, **clone (prod→QA)**, **randomize/anonymize (prod→dev)**, and **pre-production copy**
(the gated DB the CI/CD path tests against before deploy).

It realizes the "administer the full lifecycle of databases" half of the vision (§1) and the DB
side of both the dev-onboarding journey (randomized DB per client) and the instance-request
journey (QA-from-prod).

## Actor(s) served
- **Dev Jr (onboarding)** — receives a **randomized DB** of the requested client (§4 actor 1).
- **Control-plane users** — request a **QA instance generated from a given PROD** DB (§4 actor 3).
- **DevOps** — relies on the **pre-production DB copy** the update flow is gated against (§4 actor 2).

Concrete step unblocked: "get code + randomized DB" and "CI/CD runs against a pre-production DB copy".

## Port & adapters
New `Protocol` port `DatabaseProvider`, mirroring existing ports (interface-only in core, adapter in
a sibling package, lazy annotations, `runtime_checkable`):

- `provision(spec) -> DatabaseRef` — create a database and return a connection **ref** (not data).
- `clone(source_ref, target_spec) -> DatabaseRef` — full copy for a QA/pre-prod instance.
- `randomize(source_ref, target_spec, rules) -> DatabaseRef` — copy with PII anonymization applied.
- `drop(ref) -> None` — decommission a managed database.

**Candidate adapters (choose ONE at init, §Principle 3):** Dockerized Postgres (base exists,
Slice 4b) · AWS RDS · VPS Postgres. Default-at-init for the first Mirgor deployment is open (§8).

## What it reuses (does NOT build)
- The **dockerized Postgres** provisioning already delivered in Slice 4b (base for the docker adapter).
- The **cloud DB service** itself (RDS/managed PG) — backups, snapshots, HA, and PITR are the
  provider's job; the adapter drives snapshot/restore APIs rather than reimplementing them.
- Native **snapshot/clone** primitives where the target offers them (e.g. RDS snapshots) instead of
  streaming dumps by hand.
- Cloud **secret managers** for DB credentials.

## Pointers, not copies
Stores **DB connection refs** (host/name/credential handle) and lineage metadata (which PROD a QA
was cloned from), never database contents. The control plane is not a data lake (§Principle 4);
actual bytes live in the DB provider.

## Scope
- Define `DatabaseProvider` port in `odoo_forge.ports`.
- One adapter package chosen at init; import-linter forbidden contract + `root_packages` entry for it.
- Lifecycle operations: provision, clone (prod→QA), randomize/anonymize (prod→dev), pre-prod copy.
- An anonymization **rules** model (which columns/tables are PII, transformation strategy) as pure
  domain config in core; the adapter applies it dumbly.
- **Default-safe PII:** copies are **randomized/anonymized by default**. Both the QA-from-PROD
  clone and the pre-prod CI copy are anonymized unless the caller supplies **explicit, audited
  authorization** to carry real production data.
- CLI surface for lifecycle ops (foundation-level, pre-server).
- The dump/restore and anonymization **primitives** live here; their **scheduling, retention, and
  restore-drill verification** are orchestrated by **SP-10** (governance & lifecycle).

## Non-goals
- No mixing of DB backends at runtime (one adapter per init, §Principle 3).
- No schema/DDL ownership of Odoo's own databases (Odoo owns its schema).
- No control-plane state/registry (SP-4).
- No approval workflow around requests (that is SP-8).

## Dependencies
Foundation only — **Slice 4b (dockerized PG + BackendProvider)**. Independent of SP-1/SP-3.
Upstream of SP-4, SP-6, SP-7, SP-8 (§6, §7).

## Success criteria
- `DatabaseProvider` conformance test passes (`isinstance` + `inspect.signature`).
- Clone and randomize round-trip against the chosen adapter (integration-tested); anonymization
  rules verifiably transform flagged PII columns and leave others intact.
- Core stays pure: adapter covered by its own import-linter forbidden contract; purity gate green.
- Strict TDD; anonymization rules live in the pure core, the adapter is a dumb executor.

## Open decisions
- **DB randomization/anonymization rules — PII scope** for the dev/QA paths (§8). The **default is
  anonymized**; the open question is what strategy (mask/fake/nullify), who owns the ruleset per
  client, and the audited-authorization path for the rare real-PROD-data exception.
- Default-at-init DB adapter for the first Mirgor deployment (§8).
- Clone strategy: native snapshot vs. logical dump — likely per-adapter.
- Whether randomization runs inside the DB provider or in a separate sandboxed step.
