# odoo-forge

Modular Odoo platform: layered projects, declarative manifests, pluggable execution backends.

An Odoo project (core + enterprise + OCA + localization + custom addons) is a **declarative definition**, not a repository layout. Layers are versioned, published artifacts; execution environments (local Docker, IDP server, EC2, Kubernetes, Fargate) are interchangeable backends — install only what you need.

## Status

The operational implementation includes manifest and lockfile handling, Git-backed workspace
materialization, the local Docker Odoo/PostgreSQL backend, GHCR image operations, and the image
factory. The repository also contains accepted provider-neutral foundations for credentials, data
artifacts, database providers, project catalog resolution, and durable operations.

Those foundations are contracts and domain behavior, not operational adapters. In particular, the
repository does not yet contain a standalone database adapter, managed data-environment workflow,
tenancy implementation, control plane, remote backend, RBAC service, or web UI. The authoritative
status and acceptance evidence are in
[`docs/specs/platform/portfolio.json`](docs/specs/platform/portfolio.json). See the
[current implementation guide](docs/diagrams/odoo-forge-current-implementation-guide.md) for the
shipped boundary and the [complete-platform diagram](docs/diagrams/odoo-forge-complete-platform.mmd)
for target state.

## Roadmap

1. **Operational foundation** — image factory, CLI core, workspace materialization, local Docker backend, and GHCR adapter. Implemented.
2. **Provider-neutral foundations** — credentials, data artifacts, database-provider contract, project catalog, and durable operations. Implemented as contracts/domain behavior; concrete consumers remain separate work.
3. **Published layers** — schema support exists, but registry resolution and override application remain incomplete.
4. **Platform workflows** — standalone database adapter, managed data environments, tenancy, control plane, governance, and actor journeys. Planned or absent as recorded in the portfolio.
5. **Remote backends and interfaces** — EC2, Kubernetes, Fargate, RBAC, and web UI. Target state only.
