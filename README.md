# odoo-forge

Modular Odoo platform: layered projects, declarative manifests, pluggable execution backends.

An Odoo project (core + enterprise + OCA + localization + custom addons) is a **declarative definition**, not a repository layout. Layers are versioned, published artifacts; execution environments (local Docker, IDP server, EC2, Kubernetes, Fargate) are interchangeable backends — install only what you need.

## Status

The operational implementation includes manifest and lockfile handling, effective published-layer
and override resolution, Git-backed workspace materialization, materialized-state-aware backend
planning, the local Docker Odoo/PostgreSQL backend, the isolated Docker PostgreSQL
`DatabaseProvider` adapter, GHCR image operations, and the image factory.

Provider-neutral credentials, data artifacts, project-catalog resolution, and durable operations
are implemented foundations. They are not yet wired into a managed data-environment workflow.
Tenancy, a control plane, remote backends, RBAC, and a web UI remain target state. The authoritative
product status, dependencies, and acceptance evidence are in
[`docs/specs/platform/portfolio.json`](docs/specs/platform/portfolio.json); the
[current stabilization roadmap](docs/specs/2026-07-14-stabilization-roadmap.md) orders the active
work. See the [current implementation guide](docs/diagrams/odoo-forge-current-implementation-guide.md)
for the shipped boundary. The [complete-platform diagram](docs/diagrams/odoo-forge-complete-platform.mmd)
is target-state context, not a statement of current implementation.

## Roadmap

The [current stabilization roadmap](docs/specs/2026-07-14-stabilization-roadmap.md) orders the next
reviewable work. The [active OpenSpec change](openspec/changes/refresh-platform-roadmap-after-stabilization/proposal.md)
tracks this reconciliation; [`sp-data-environments`](openspec/changes/sp-data-environments/proposal.md)
remains blocked. `docs/specs/platform/portfolio.json` remains authoritative for product status and
dependencies.

1. **Operational foundation** — image factory, CLI core, workspace materialization, local Docker backend, Docker PostgreSQL adapter, and GHCR adapter. Implemented.
2. **Provider-neutral foundations** — credentials, data artifacts, `DatabaseProvider`, project catalog, and durable operations. Implemented; managed consumers remain separate work.
3. **Published layers** — version/digest resolution and Git overrides are implemented.
4. **Platform workflows** — managed data environments, tenancy, control plane, governance, and actor journeys. Blocked, planned, or absent as recorded in the portfolio.
5. **Remote backends and interfaces** — EC2, Kubernetes, Fargate, RBAC, and web UI. Target state only.
