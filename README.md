# odoo-forge

Modular Odoo platform: layered projects, declarative manifests, pluggable execution backends.

An Odoo project (core + enterprise + OCA + localization + custom addons) is a **declarative definition**, not a repository layout. Layers are versioned, published artifacts; execution environments (local Docker, IDP server, EC2, Kubernetes, Fargate) are interchangeable backends — install only what you need.

## Status

Phase 0 — design. See [the product design spec](docs/specs/2026-07-05-modular-odoo-platform-design.md).

## Roadmap

1. **Image factory** — multi-version Odoo base images, built and published by CI.
2. **CLI core** — `project.yaml` manifest, workspace materialization, local backend.
3. **Published layers** — enterprise/OCA/localization as versioned artifacts with per-layer access control.
4. **Control plane** — instance lifecycle server (dev/QA spawning, backups, governance).
5. **Remote backends** — EC2, Kubernetes, Fargate.
