# Exploration: CAP-PROJECT-CATALOG — Project Catalog Capability

`CAP-PROJECT-CATALOG` is still a valid, independent Wave 1 prerequisite in the authoritative platform portfolio. This fresh start keeps it explicitly separate from `CAP-DATA-ARTIFACTS`, `CHG-FIRST-DATABASE-ADAPTER`, and `SP-DATA-ENVIRONMENTS`: it owns **project/client resolution**, not data movement, database lifecycle, or environment orchestration.

## Current authority

- `docs/specs/platform/portfolio.json` is the normative planning authority per `openspec/specs/platform-subproject-governance/spec.md`.
- The accepted portfolio-integrity specs require the plan to keep dependency edges concrete, scopes disjoint, and prerequisite capabilities separate.
- The archived platform redefinition remains the authoritative rationale for introducing `CAP-PROJECT-CATALOG` as a Wave 1 prerequisite: **client/project to manifest, source, data policy, and target defaults resolution**.
- The roadmap/redefinition evidence places this capability under later consumers such as `SP-DEVELOPER-ONBOARDING` and `SP-ENVIRONMENT-REQUESTS`, not under the current database-adapter or data-artifact delivery chain.

## Current state

- The codebase already has manifest, source-resolution, workspace-materialization, and local backend foundations.
- `src/odoo_forge/manifest/schema.py` models a single manifest and client payload, but there is no catalog-level concept for resolving a project/client request into the right manifest, source set, data policy, or target defaults.
- `src/odoo_forge/ports/source_provider.py` and `src/odoo_forge/ports/workspace_provider.py` provide lower-level source/workspace primitives, but nothing composes them through a project catalog boundary.
- `src/odoo_forge/backend/plan.py` still plans one local backend directly from one manifest; it does not consume any project-catalog decision or target-default contract.
- No current OpenSpec change defines the catalog authority, lookup keys, conflict rules, fallback behavior, or the exact boundary between project metadata and later control-plane/request workflows.

## Exact problem statement

The platform has the low-level pieces to read a manifest, resolve source refs, materialize workspaces, and run a local backend, but it still lacks the capability that answers a higher-level product question:

**Given a client/project request, how does the platform deterministically resolve the authoritative manifest, source context, data-policy default, and target default without leaking that responsibility into onboarding flows, environment requests, or control-plane internals?**

Without that capability:

- `SP-DEVELOPER-ONBOARDING` cannot reliably turn a client/project request into editable source plus the correct environment intent.
- `SP-ENVIRONMENT-REQUESTS` would be forced to invent project lookup and defaulting rules inside workflow code.
- `SP-CONTROL-PLANE-AUTHORITY` risks absorbing product-catalog semantics that should exist as an explicit prerequisite contract.
- Source, data-policy, and placement defaults could drift across future consumers.

## Dependencies

### Required inputs

- `docs/specs/platform/portfolio.json` — authoritative identity, edges, and prerequisite ownership.
- `openspec/specs/platform-subproject-governance/spec.md` and `openspec/specs/platform-portfolio-documentation-integrity/spec.md` — authority and disjoint-scope rules.
- Existing manifest/source/workspace foundations:
  - `src/odoo_forge/manifest/schema.py`
  - `src/odoo_forge/ports/source_provider.py`
  - `src/odoo_forge/ports/workspace_provider.py`
- Archived platform redefinition evidence for the original capability intent and downstream consumers.

### Downstream consumers

- `SP-DEVELOPER-ONBOARDING`
- `SP-ENVIRONMENT-REQUESTS`
- likely `SP-CONTROL-PLANE-AUTHORITY` integration points where canonical project resolution must be consumed, not reinvented

### Important adjacent but separate changes

- `CAP-DATA-ARTIFACTS` — database/filestore capture refs, checksums, consistency, validation, discard
- `CHG-FIRST-DATABASE-ADAPTER` — first database adapter after its own prerequisite gates
- `SP-DATA-ENVIRONMENTS` — managed data-environment outcome
- `CAP-TENANCY`, `CAP-PROVIDER-CATALOG`, and `CAP-DEPLOYMENT-SPEC` — adjacent prerequisites with different ownership boundaries

## Non-goals

This change should NOT:

- define database/filestore artifact capture or restore contracts
- define anonymization mechanics or data-copy orchestration
- implement the first database adapter or runtime cutover
- define tenancy, RBAC, approval, or audit policy
- choose provider adapters or own provider-catalog registration
- implement control-plane persistence, API transport, or request workflows
- collapse onboarding or environment-request product flows into the prerequisite itself

## Why this is safe to advance in parallel

`CAP-PROJECT-CATALOG` is a **separate concern boundary**.

- The active database/data-environment chain is blocked by `CAP-DATA-ARTIFACTS`, `CAP-CREDENTIALS`, `PORT-DATABASE-PROVIDER`, and downstream environment/control-plane handoffs — not by project catalog work.
- The catalog capability sits closer to manifest/source/workspace resolution than to database lifecycle or artifact consistency.
- A contract-first exploration/proposal for this capability can proceed without mutating the meaning of `CAP-DATA-ARTIFACTS`, `CHG-FIRST-DATABASE-ADAPTER`, or `SP-DATA-ENVIRONMENTS`.
- Keeping it separate reduces future scope bleed: later onboarding/request changes can consume one explicit project-resolution contract instead of rebuilding ad hoc lookup rules.
- Under the forced chained strategy and 400-line review budget, this capability is naturally sliceable as planning/contract work before any broad workflow implementation.

The main risk is not parallelism — it is **scope creep**. If the proposal tries to absorb request orchestration, data policy engines, or control-plane persistence, it stops being safe.

## Recommendation

Advance `CAP-PROJECT-CATALOG` as its own prerequisite SDD, but keep it contract-first and strictly bounded to authoritative project/client resolution.

The proposal should answer:

1. What identifiers select a project/client record?
2. What authoritative outputs are resolved (manifest, source context, data-policy default, target default)?
3. Which fields are catalog-owned versus delegated to tenancy, deployment, data, or workflow capabilities?
4. How do consumers read the result without duplicating lookup/defaulting logic?
5. What remains explicitly deferred to onboarding, environment requests, and control-plane authority?

## Ready for proposal

Yes.

The capability intent, authority source, lower-level foundations, downstream consumers, separation from active database/data changes, and major non-goals are clear enough to draft a bounded proposal.