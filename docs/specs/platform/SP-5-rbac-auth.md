# SP-5 — RBAC / auth

> **Historical brief (superseded).** Preserved for SP-era design lineage. Use
> [`portfolio.json`](portfolio.json) for current status, evidence, dependencies, and handoffs.

**Layer:** Orchestration · **Status:** planned · **SDD change name (proposed):** `platform-rbac-auth`

## Purpose
This sub-project adds **authentication and role-based access control** to the control plane. It
does **not** build user management — it **reuses** an existing organization identity provider via
OIDC/SSO (GitHub / GitLab / Google org) and maps authenticated identities onto the platform's
functional roles: **functional, devops, customer, CTO** (§4 actor 3). Authorization then gates the
control-plane API and, by extension, the instance-request and control-panel experiences.

This is the smallest possible auth layer consistent with §Principle 2 (reuse existing infra): the
IdP is the orchestra; the server only decides *what each role may do*.

## Actor(s) served
**Control-plane users** with distinct roles (§4 actor 3) — functional, devops, customer, CTO — and
DevOps operating the panel (§4 actor 2). Unblocks: "Request a new PROD instance, a QA instance from
a given PROD, or a randomized DEV instance" being **scoped by role**.

## Port & adapters
Orchestration over SP-4's API. The IdP integration is itself a **port with a chosen-at-init adapter**
(§Principle 3): an `IdentityProvider` (OIDC) port with GitHub / GitLab / Google-org adapters. Only
one IdP is bound at init. Role assignment (identity/group → platform role) is pure domain policy in
core; the adapter only performs the OIDC handshake and returns claims.

## What it reuses (does NOT build)
- **OIDC/SSO from GitHub / GitLab / Google org** — login, credentials, MFA, account lifecycle are the
  IdP's job (§3 "what else is reused").
- **No user management** — the platform stores role *mappings*, not user accounts or passwords.
- SP-4's API and instance registry as the thing being protected.

## Pointers, not copies
Stores role **mappings** (external identity/group ref → platform role) and session/token references
only — no passwords, no mirrored user directory (§Principle 4). Identity truth stays in the IdP.

## Scope
- `IdentityProvider` (OIDC) port + one adapter chosen at init; import-linter forbidden contract +
  `root_packages` entry for the adapter package.
- Role model (functional / devops / customer / CTO) as pure domain policy.
- Authorization enforcement on the SP-4 API (per-role permissions for instance operations).
- Session/token handling delegated to the OIDC flow.

## Non-goals
- No user CRUD, password storage, or account lifecycle (owned by the IdP).
- No UI (that is SP-9).
- No per-record data-level ACLs inside Odoo instances (Odoo owns its own security).
- No multiple simultaneous IdPs at runtime (one adapter per init, §Principle 3).

## Dependencies
Upstream: **SP-4** (the API + registry to protect) (§6, §7). Downstream: SP-8 (role-gated requests),
SP-9 (role-aware panel).

## Success criteria
- OIDC login round-trips against the chosen IdP adapter; claims map to the correct platform role.
- API endpoints enforce role permissions (a customer cannot perform a devops-only operation) —
  verified by authorization tests.
- No user credentials are persisted anywhere in the platform (verified by inspection/test).
- Role policy lives in the pure core and is import-linter-clean; the OIDC adapter is a dumb shell.
  Strict TDD throughout.

## Open decisions
- Which IdP is **default-at-init** for the first Mirgor deployment (GitHub / GitLab / Google org).
- Mapping source: IdP groups/teams vs. an explicit platform-side role table.
- Granularity of the permission model (coarse per-role vs. per-operation capabilities).
