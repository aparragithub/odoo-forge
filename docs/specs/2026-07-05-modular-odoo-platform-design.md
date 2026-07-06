# Modular Odoo Platform — Product Design

**Date:** 2026-07-05
**Status:** Approved design, pre-implementation
**Origin:** Architecture audit of `odoo-idp` (4-agent analysis) + brainstorming session
**Home:** This document seeds the new product repository. It lives temporarily in `odoo-idp` and moves to the new repo when it is created.

## 1. Problem Statement

`odoo-idp` is a well-built control plane for **one** deployment: one Odoo version (19.0 hardcoded across Dockerfile, `.gitmodules`, `repos.yaml`, CLI), one shared addon tree (`src/addons/*`), one client's localization wired into the repo, one Docker daemon, one domain, one global `.env`. "Organizations" and "projects" are naming labels in SQLite, not provisioning units.

Root cause: **the client project does not exist as data.** The repository itself is the project. Supporting a second client or a second Odoo version means forking the whole repository — that is where modularity dies.

The goal is a product where:

- An Odoo project (core + enterprise + OCA + localization + community + custom addons) is a **declarative definition**, not a filesystem state.
- Execution environments are **pluggable backends**: local Docker, IDP server, EC2, Kubernetes, Fargate. You install only the piece you need.
- Junior devs spin up a working instance with one command; ops teams manage N clients × M environments because every dimension is data.

## 2. Product Shape: Three Contracts

The product is a small core that defines three contracts, plus interchangeable implementations around them.

### 2.1 The Onion — layer model

An Odoo project is a chain of **layers**:

```
community 19  →  enterprise 19  →  OCA 19  →  localization  →  client
```

Rules:

- Each layer is a **versioned, published artifact**. The next layer **consumes** it; it never builds it.
- Access control lives where the artifact lives (registry / private repo). A developer without an enterprise license cannot pull the enterprise layer. No access logic in the tool itself.
- A partial onion is still a product: `community 19` alone is usable; `community + OCA` is usable; and so on.
- Layer producers: the platform team builds and publishes base layers (community/enterprise/OCA per Odoo version). Client teams publish only their final layer and consume the rest.

### 2.2 A layer is a definition with two projections

A layer is **not** an image and **not** a source tree. It is a **definition** — sources plus pinned versions — from which two projections are derived:

| Projection | Consumer | Form |
|---|---|---|
| **Image** | Servers (IDP server, EC2, K8s, Fargate) | Baked, immutable, runnable artifact |
| **Workspace** | Developers (local) | Source checkouts of ALL layers at the exact pinned versions, mounted into the container |

Same manifest, same truth, two materializations.

Developer visibility and write boundaries:

- All layers materialize as **source** on the dev machine — readable, debuggable, breakpoint-able. Devs must be able to trace a bug into OCA or Odoo core.
- Lower layers are **read-only by default**. The client layer is writable.
- **Explicit unlock**: when a bug belongs to a lower layer, the tool converts that layer's checkout into a working branch (fork/worktree). Two legitimate exits:
  1. **Fix in the client layer** (module inheritance / override) when applicable.
  2. **Fix in the lower layer**: PR to that layer's repo → new layer version published → projects bump their pin. While the PR travels, the manifest may declare a `patch` or temporarily point that layer to a fork (pattern inherited from `odoo-idp`'s `replaced_repo_source_id`).

### 2.3 The Manifest — `project.yaml`

A client project is a small repository containing its custom addons plus a manifest declaring everything else. Draft schema (to be formalized in Phase 0 → 2):

```yaml
name: acme
odoo_version: "19.0"
edition: enterprise            # community | enterprise

layers:                        # consumed layers, pinned
  - name: enterprise
    source: registry://.../odoo-ee
    version: "19.0.2026-06-01"
  - name: oca
    source: registry://.../oca-base
    version: "19.0.14"
  - name: l10n-ar
    repos:
      - url: git@github.com:ingadhoc/odoo-argentina.git
        ref: "19.0"

client:                        # this repo's own addons
  addons_path: ./addons
  python_requirements: ./requirements-extra.txt

overrides:                     # temporary forks / patches of lower layers
  - layer: oca
    repo: OCA/account-financial-tools
    fork: git@github.com:acme/account-financial-tools.git
    ref: fix/invoice-rounding
```

Companion **lockfile** (`project.lock`): fully resolved refs (commit SHAs, image digests) so both projections are reproducible. Manifest = intent; lockfile = resolution. Drift between manifest, lockfile, and materialized state is a first-class validation (pattern inherited from `odoo-idp`'s `validate_catalog`).

### 2.4 The Backend Contract — core + providers

The core defines abstract operations; each backend implements them and declares its capabilities:

```
materialize(project, projection) -> workspace | image ref
create_instance(project, env)    -> instance
destroy(instance)
logs(instance)
exec(instance, cmd)
backup(instance) / restore(instance, snapshot)
status(instance)
```

Capability declaration per backend:

| Backend | Delivery modes | Notes |
|---|---|---|
| `local` (Docker) | workspace (mounts), image | Dev feedback loop; first backend built |
| `idp-server` | image, workspace | The current spawn-manager concept, re-homed |
| `ec2` | image | |
| `kubernetes` | image | No host tree to mount |
| `fargate` | image | No host tree, no daemon |

Backends are installable independently ("you need local — take it; you need Fargate — take it"). The contract is proven against two real backends (local, idp-server) **before** any remote backend is designed.

## 3. Layer Materialization: Two Models to Evaluate

Deliberately undecided. The spec mandates evaluating both with a proof of concept before Phase 3.

### Model A — Chained Docker images

`odoo-ce:19` → `odoo-ee:19` (FROM ce) → `oca:19` (FROM ee) → `client` (FROM oca).

- **Pros:** immutable, cacheable, registry-native access control per layer, trivially runnable on any container backend, digest pinning for free.
- **Cons:** linear chain forces an ordering (what if a project wants OCA without enterprise? — may require parallel chains per edition); image rebuild cascade when a low layer bumps; large artifacts.

### Model B — Base image per version + layers as packages

One image per Odoo version; each layer (enterprise, OCA set, localization, client) is a versioned package installed at compose time (precedent: OCA publishes addons to PyPI as `odoo-addon-*`).

- **Pros:** granular, light, no chain-ordering problem, natural dependency resolution per addon.
- **Cons:** composition happens at consumer build/runtime (weaker immutability unless a final image is still baked); enterprise is not pip-installable today; private package index infra needed; dependency resolution complexity.

### Decision criteria

1. Can a project skip a layer (community + OCA, no enterprise) without artifact duplication?
2. Cost of a low-layer bump (rebuild cascade vs re-resolve).
3. Access-control fit (registry pull rights vs package index auth).
4. Reproducibility guarantees (digest vs resolved package set).
5. Operational complexity for the platform team.

PoC: build the same small project (community + 2 OCA repos + 1 custom addon) both ways; measure the five criteria. Hybrid outcomes are acceptable (e.g., packages for composition, final baked image per project for remote backends).

## 4. Access Model

- Every developer uses their **own** GitHub/GitLab identity with scoped access.
- Layer artifacts enforce access at their storage (registry pull permissions, private repo membership).
- A dev may have access to the client repo only: they can still work — they pull/consume published layer artifacts (or public source for community layers) and never need image-factory access.
- The image factory is a consumed service: devs call it or download from it; they do not build base layers.

## 5. Reuse Map from `odoo-idp`

### Reuse now (design and early phases)

| Piece | Location in odoo-idp | How it is reused |
|---|---|---|
| Dynamic `addons_path` discovery | `infra/build/entrypoint.sh` | Nearly as-is — core of the workspace projection |
| Multi-stage Dockerfile, layered pip installs | `infra/build/Dockerfile` | Image factory base, parameterized with `ARG ODOO_VERSION` |
| "One image, two environments" pattern | entrypoint + runtime config injection | Product design principle |
| `RepoSource`/`ProjectRepoBinding` schema (`replaced_repo_source_id`) | `platform/web/models/repo_source.py` | Informs manifest schema: per-layer pins, per-project overrides |
| Drift detection (`validate_catalog`) | `platform/cli/idp_scripts/services/repo_catalog.py` | Becomes manifest ↔ lockfile ↔ filesystem validation |
| Per-instance compose override generation | `platform/cli/idp_scripts/services/compose_service.py` | Direct reference for the `local` backend |

### Reuse later (when the control plane exists)

- Backup service (local/R2/MinIO backends, scheduled cron, retention, restore drills).
- Governance: `policies.yaml`, append-only audit trail, PROD instance guardrails, gated promotions.
- Canonical-ID instance registry + strict relational-ID (FK) discipline — principle from day 1, code later.
- Taskfile DX patterns and `task doctor` — models for the new CLI's UX.

### Consciously left behind

- Umbrella repo with submodules and global `repos.yaml` — replaced by the manifest.
- Hardcoded `ADDON_LAYERS`, single `odoo-idp-odoo` image tag, shared `src/addons/*` tree.
- Dual build paths (`buildx` in Taskfile vs broken `docker compose build odoo` in `DockerService.build_odoo()`).
- Dual DDL definitions (CLI raw-sqlite registry vs web SQLModel schema).

## 6. Technical Architecture

### 6.1 Style: hexagonal (ports and adapters), screaming structure

The product shape maps 1:1 onto hexagonal architecture:

- **Domain (core)**: `Layer`, `Manifest`, `Lockfile`, `Project`, `Instance`, the two projections. Pure logic — pin resolution, drift validation, onion composition. Zero infrastructure dependencies.
- **Ports**: the backend contract (§2.4), the artifact store (registry/package index), the source provider (git hosts), configuration.
- **Adapters**: `local` (Docker), `idp-server`, `ec2`, `kubernetes`, `fargate`; GitHub/GitLab as source-provider adapters.

Hard rule, enforced by import-linter (or equivalent) in CI: **the core never imports `docker`, `boto3`, `kubernetes`, or any git host SDK.** If it does, the architecture is broken.

Package layout screams the domain, not the framework:

```
odoo_forge/
  layers/        # onion model, composition
  manifest/      # project.yaml + lockfile schema, resolution, drift
  backends/      # the port (contract) + capability declarations
  workspace/     # source projection materialization
  images/        # image projection (factory client)
cli/             # Typer entry points (thin; delegates to core)
backends_local/  # separate package: Docker adapter
backends_k8s/    # separate package (later)
```

Backends ship as **separate installable packages** discovered via Python entry points (`odoo_forge.backends` group) — this is the mechanism behind "install only what you need".

### 6.2 State model: no database in the CLI

- **CLI core (Phase 2): no database.** State is the manifest + lockfile (versioned in git) plus **backend introspection** (Docker labels, K8s resources). To know which instances run, ask the backend — never a parallel registry file that can drift. Rationale: `odoo-idp`'s dual DDL (CLI SQLite registry vs web SQLModel) already produced drift and required the `mer-fk-refactor` effort.
- **Control plane (Phase 4): PostgreSQL.** Users, audit trail, policies, backup schedules — real server-side state. Postgres already exists in every deployment for Odoo itself.
- SQLite is never a shared database; at most a disposable local cache.

### 6.3 Stack

- **Python 3.12+**, managed with **uv**. CLI with **Typer**, schemas with **Pydantic v2**.
- Rationale: it is the language of the Odoo ecosystem — client-team devs can contribute to the tool — and the reusable `odoo-idp` code (compose generation, backup, catalog validation) ports directly. Distribution via `uvx` / `pipx`.
- Trade-off accepted: not a single static binary (Go's advantage). Revisit only if distribution pain appears in remote-backend phases.

### 6.4 Multi-OS requirement

Supported developer platforms: **Ubuntu, Arch, macOS, Windows.**

- The CLI is identical everywhere (uv runs on all four).
- The real multi-OS difficulty is the **local backend**, not the language: Docker on macOS/Windows runs inside a VM (Docker Desktop / WSL2), and bind mounts — the workspace projection — have poor filesystem performance on macOS and different path semantics on Windows.
- This is an adapter concern: the `local` adapter selects a per-OS mount strategy (native binds on Linux; Docker Desktop with sync/volume strategies on macOS; WSL2-required on Windows, workspace materialized inside the WSL filesystem).
- A `doctor` command (pattern inherited from `odoo-idp`) validates each OS environment before first use.

## 7. Roadmap

Each phase ships something usable on its own.

- **Phase 0 — This spec.** Layer model, manifest + lockfile schema, backend contract, access model, Model A/B analysis with PoC plan.
- **Phase 1 — Image factory.** Parameterized Dockerfile (`ARG ODOO_VERSION`), per-version tags (`odoo-ce:19`, `odoo-ce:18`), registry, CI that builds and publishes. Standalone value: multi-version base images exist even if nothing else does. Done — see the [Phase 1 design](2026-07-05-phase-1-image-factory-design.md).
- **Phase 2 — CLI core + manifest + local backend.** CLI reads `project.yaml`, materializes the workspace (pinned checkouts, lower layers read-only, unlock mechanism), runs the instance on local Docker. A junior dev runs one command in the client repo and gets a working Odoo.
- **Phase 3 — Published layers.** Enterprise/OCA/localization published as versioned layers per the PoC winner. Granular access via registry/repo permissions.
- **Phase 4 — Control plane.** IDP server as the second backend: spawns dev/QA instances from manifests. Backup, governance, and audit ported from `odoo-idp` here.
- **Phase 5 — Remote backends.** EC2, Kubernetes, Fargate — designed against a contract already proven by two real backends.

**Migration fire test:** `odoo-idp` keeps running as-is and becomes the first client migrated onto the product once Phase 2 is solid. If the manifest cannot express that real project, the manifest is wrong.

## 8. Known Bugs in odoo-idp (do not carry over)

Found during the audit; listed so they are not inherited by copy-paste:

- `DockerService.build_odoo()` runs `docker compose build odoo`, but no compose file defines an `odoo` build service — dead/broken path.
- `ODOO_UID`/`ODOO_GID` build args are declared in the Dockerfile but never passed to `docker buildx build`; images always bake UID/GID 1000.
- `requirements.collected.txt` is a checked-in generated artifact with no freshness enforcement at build time.

## 9. Open Questions

1. Model A vs Model B (resolved by the Phase 3 PoC; criteria in §3).
2. Lockfile update workflow (who bumps pins, how promotions interact with pinned versions).
3. Enterprise licensing/distribution constraints on publishing an enterprise layer artifact (legal review before Phase 3).
4. Python dependency strategy per layer (each layer ships its resolved requirements vs project-level final resolution).
