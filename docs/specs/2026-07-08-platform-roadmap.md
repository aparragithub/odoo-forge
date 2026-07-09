# odoo-forge — Platform Roadmap (Internal Odoo PaaS)

**Status:** living document · **Created:** 2026-07-08.

This document is the forward map for evolving `odoo-forge` from a local CLI into an
**internal Odoo Platform-as-a-Service** (Odoo.sh / Heroku-style, self-hosted). It defines
the vision, the governing principles, the actors served, and the decomposition into
independent sub-projects (SP-1 … SP-10), each delivered as its own SDD change.

> **Naming.** Sub-projects use `platform-*` SDD change names and SP-N identifiers, not the
> founding Phase-3/4 numbers. Mapping: SP-4..SP-10 realize the founding "Phase 4 control
> plane" (design line 228); the founding "Phase 3 published layers" (design line 253) is
> superseded — its `PublishedLayer` source-resolution is deprecated (see §8 Deprecations),
> its pre-built-image intent is realized by SP-1.

> Companion diagram: `docs/specs/platform/platform-architecture.html`.

---

## 1. Vision

A central **control plane** (`forge server`) that takes code from repositories, fabricates
artifacts, and satisfies requests from three actor profiles — delivering either **pre-built
Docker images** (server instances) or **editable source + a database** (dev instances),
across multiple deployment targets, while administering the full lifecycle of databases.

The server is a **conductor, not the orchestra**: it coordinates infrastructure that already
exists (git hosts, image registries, cloud DBs, deploy targets, CI/CD, IdPs) through one
pluggable adapter per concern, and remembers only **pointers** and **which instance runs
where**.

---

## 2. Governing Principles (non-negotiable)

1. **Repo-only provenance.** Only code that lives in a repository runs. Nothing deploys
   outside the `git → CI` path. No ad-hoc artifacts.
2. **Reuse existing infrastructure via ports & adapters (hexagonal).** Every external
   concern is a **port** (interface) with interchangeable **adapters**. This is the pattern
   the project already uses (`SourceProvider`+git, `BackendProvider`+docker).
3. **One adapter per port, chosen at init.** The composition root selects a single adapter
   per concern at initialization. Concerns are **not** distributed/mixed across providers at
   runtime. (Same anti-drift discipline as the single canonical lockfile / instance registry.)
4. **Store pointers, not copies.** The server references repo URLs, image **digests**, and DB
   connection refs. It is **not** a data lake. `project.lock` already models this: it pins
   references and stores nothing.
5. **Anti-drift state.** State (the canonical instance registry) lives in one place with
   strict FK discipline — never duplicated DDL. (Rationale: the `odoo-idp` dual-DDL drift that
   forced `mer-fk-refactor`.) This does **not** contradict the founding "no database" note,
   which was scoped to the Phase-2 CLI core (design line 227); server-side state was always
   anticipated by the founding **canonical registry** (design line 187) and the **Phase-4
   PostgreSQL control plane** (design line 228: "Users, audit trail, policies, backup
   schedules — real server-side state"). Design line 195 ("web SQLModel schema") is the
   **abandoned** dual-DDL pattern under "Consciously left behind" — the drift we must NOT
   repeat, not evidence the server was anticipated.

---

## 3. Ports & Adapters map

| Concern | Port | Adapters (choose ONE at init) | Status |
| --- | --- | --- | --- |
| Module / Odoo source code | `SourceProvider` | GitHub · GitLab · external repos | **git DONE** (Slice 2b) |
| Docker images | `ImageRegistryProvider` *(new, SP-1)* | GHCR · GitLab Registry · AWS ECR · DockerHub | Phase 1 publishes to GHCR |
| Databases | `DatabaseProvider` *(new, SP-2)* | Dockerized PG · AWS RDS · VPS Postgres | **dockerized PG DONE** (Slice 4b) |
| Deploy target | `BackendProvider` | Docker local · EC2/VPS · Fargate · K8s | **docker local DONE** (Slice 4b) |
| Identity / SSO | `IdentityProvider` *(new, SP-5)* | GitHub org · GitLab org · Google Workspace (OIDC) | reused IdP |
| CI/CD pipelines | `PipelineProvider` *(new, SP-6)* | GitHub Actions · GitLab CI | reused engine |

Note: even **reused** concerns (identity, CI/CD) are modeled as adapter-pattern ports so
Principle 3 (one adapter chosen at init) applies uniformly — reuse means we do not build the
engine, not that it escapes the port abstraction.

**What else is reused (not a port):** secrets (cloud secret managers), DNS/ingress/TLS
(target-native: ALB, ingress-nginx, Traefik), observability (target-native: CloudWatch, etc.).

Every new adapter lives in its own sibling package. There are **5 import-linter contracts
today** (1 generic external-import ban + 1 CLI ban + 3 per-adapter-package bans for
`odoo_forge_git`, `odoo_forge_workspace`, `odoo_forge_docker`); each new adapter package adds
one per-package ban (SP-1 adds the 6th total, and SP-2/SP-3/SP-5/SP-6 each add their own
thereafter).

---

## 4. Actors served

1. **Dev Jr (onboarding).** Requests an environment by client → receives **code + a
   randomized DB** of that client → develops locally → pushes to a repo → CI → on pass the
   server builds images and does CD.
2. **DevOps (operations).** Views a control panel of instances per server → decides to apply
   an update → **CI/CD runs against a pre-production DB copy** → on pass, deploys to the
   corresponding target (EC2/VPS/Fargate/K8s).
3. **Control-plane users (RBAC: functional, devops, customer, CTO, …).** Request a new
   **PROD** instance, a **QA** instance generated from a given PROD, or a **randomized DEV**
   instance for general flow testing.

---

## 5. Foundation already built

- **Phase 1 — Image factory:** parameterized base images published to GHCR, digest-pinned.
- **Phase 2 Slice 1 — Manifest core:** Pydantic schema, onion composition, `SourceProvider`
  port, purity gate.
- **Phase 2 Slice 2a/2b — Resolution:** canonical lockfile, git `SourceProvider` adapter,
  `forge lock`.
- **Phase 2 Slice 3 — Workspace projection:** `plan_projection`, `materialize_state`,
  `WorkspaceProvider`, `forge project` / `forge unlock`.
- **Phase 2 Slice 4b — Local Docker backend:** `BackendProvider` port + docker adapter +
  dockerized PG, `forge run/status/stop/logs/exec`.

---

## 6. Decomposition — sub-projects

Each sub-project is an independent SDD change (proposal → spec → design → tasks → apply →
verify → archive). Detailed per-sub-project briefs live in `docs/specs/platform/SP-*.md`.

### Layer 1 — Ports & adapters (extend the hexagon)

| # | Sub-project | Adds | Depends on |
| --- | --- | --- | --- |
| **SP-1** | `ImageRegistryProvider` | Port + first adapter; publish + pull layer images by digest. Enables the pre-built-image model. | Foundation (Phase 1) |
| **SP-2** | `DatabaseProvider` + DB lifecycle | Port + adapters (dockerized/RDS/VPS); provisioning + clone (prod→QA), randomize/anonymize (prod→dev), pre-prod copy. | Foundation (4b) |
| **SP-3** | Remote `BackendProvider` adapters | Targets beyond local docker: EC2/VPS → Fargate → K8s (one per slice). | Foundation (4b) |

### Layer 2 — Orchestration (the control plane)

| # | Sub-project | Adds | Depends on |
| --- | --- | --- | --- |
| **SP-4** | Control plane core | API + canonical instance registry (state) + per-port config (choose-one-at-init). | SP-1/2/3 |
| **SP-5** | RBAC / auth | Roles (functional/devops/customer/CTO) via reused OIDC/SSO. | SP-4 |
| **SP-6** | CI/CD integration | Trigger/read GH Actions/GitLab CI; `push→CI→build→CD`; deploy gated by pre-prod DB test. | SP-1, SP-2, SP-3, SP-4 |
| **SP-10** | Governance & lifecycle | Append-only audit trail + PROD guardrails/gated promotions; GC/retention (TTL for DEV/QA clones & instances, digest retention, orphan reclamation); backup orchestration + restore drills. | SP-4 (+ SP-1/2/3 ports it reclaims) |

### Layer 3 — Experience (actor journeys)

| # | Sub-project | Adds | Depends on |
| --- | --- | --- | --- |
| **SP-7** | Dev onboarding flow | Request env by client → source delivery + randomized DB → develop. | SP-2, SourceProvider, SP-4 |
| **SP-8** | Instance lifecycle requests | Request PROD / QA-from-prod / randomized-DEV. | SP-2/3/4/5 |
| **SP-9** | Control panel (web UI) | The panel devops/functional/CTO operate. | SP-4 (+5) |

---

## 7. Recommended build order

Ports first, then the orchestrator, then the experience:

```
SP-1 → SP-2 → SP-3   (ports & adapters — independent, extend the proven hexagon)
        ↓
SP-4 → SP-5          (control plane core + RBAC)
        ↓
SP-6                 (CI/CD integration)
        ↓
SP-10                (governance, audit, GC/retention, backup orchestration)
        ↓
SP-7 → SP-8 → SP-9   (actor experiences)
```

Rationale: the control plane only pays off once it has ports to orchestrate; the experience
layer composes the ports + orchestration. Ports are independently valuable and testable on
their own (each usable from the CLI before the server exists).

---

## 8. Open decisions (to resolve per sub-project)

- Which adapter is the **default at init** for each new port (image registry, DB, remote
  backend) for the first Mirgor deployment.
- Control plane transport/stack (API framework, persistence for the instance registry) —
  grounded in the founding **Phase-4 PostgreSQL control plane** (design line 228), NOT the
  abandoned "web SQLModel schema" dual-DDL pattern (design line 195).
- DB randomization/anonymization rules (PII scope) — owned by SP-2 but spans SP-2 (dev DB),
  SP-6 (pre-prod test data), and SP-8 (QA-from-PROD: real vs. randomized data). Default is
  **anonymized**; real PROD data requires explicit, audited authorization.
- Whether SP-3 ships one target at a time (recommended) or a batch.
- **Principle 3 scope** — "one adapter per port at init" vs. a central control plane deploying
  to multiple targets/clients simultaneously — under separate discussion; likely resolution is
  to scope Principle 3 (foundation/CLI = one-at-init; control plane = per-instance adapter
  selection from a registered set), but NOT yet decided.

### Deprecations

- The **`PublishedLayer`** source arm (`src/odoo_forge/manifest/schema.py:33-39`,
  `src/odoo_forge/manifest/locking.py:32-34`) is **DEPRECATED**. It was a `SourceProvider`
  source-resolution concern (the abandoned "Slice 4a `registry://`" idea), not a container-image
  registry. The real needs are covered by **`GitLayer`** (enterprise-fork source) and
  **pre-built images** (SP-1). Schedule its removal as a small cleanup change.

---

## 9. Cross-references

- Founding design: `docs/specs/2026-07-05-modular-odoo-platform-design.md` (lines 34-35, 126,
  185-187, 195, 227, 228, 253).
- Phase 2 slices: `docs/specs/2026-07-06-phase-2-slices-roadmap.md`.
- Prior "Slice 4a" exploration (`PublishedLayer` source-resolution, now DEPRECATED — see §8
  Deprecations; unrelated to SP-1's container-image concern):
  `openspec/changes/phase-2-slice-4a-registry-resolution/explore.md`.
- Engram: `odoo-forge/platform-vision` (#2361).
