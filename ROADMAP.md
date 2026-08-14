# Roadmap

This page is a human-readable projection of the canonical product state in
[`docs/specs/platform/portfolio.json`](docs/specs/platform/portfolio.json).
When the two disagree, the portfolio wins.

odoo-forge is maintained by one person and carries **no dates**. Tiers below
express order and intent, not promises.

## ✅ Working today

You can use all of this right now, end to end:

| Capability | What it gives you |
| --- | --- |
| Manifest core | `project.yaml` validated and composed into an effective project definition |
| Source resolution | Every declared Git ref locked to an exact commit SHA (`project.lock`), with drift detection |
| Workspace projection | Locked manifests materialized onto disk under fixed mount roots, Git-backed |
| Local backend | Odoo + PostgreSQL provisioned on local Docker from the materialized state (`run` / `status` / `stop` / `destroy` / `logs`) |
| Image registry | GHCR operations: resolve to digest, publish, prefetch, existence checks — plus the base-image factory |
| Credential materialization | SOPS/age-backed Enterprise credentials, with `doctor` checks and key rotation |
| Developer onboarding | `onboard` validates and materializes local inputs, or resolves a catalog-known client to a running instance |
| Guided manifest authoring | `manifest create` produces a validated `project.yaml` through a terminal wizard |

## 🧱 Built, not yet wired

These foundations are implemented and tested, but not yet exposed as managed,
end-to-end workflows:

- **Data artifacts** — capture/restore primitives for database content, including dump masking
- **Durable operations** — resumable long-running operation records
- **Resource ownership** — authority over which actor owns which runtime resource
- **Tenancy contract** — customer/client boundaries and quota model
- **Project catalog** — the index that lets `onboard <client>` resolve a client to its manifest
- **Remote deployment handoff** — provider-neutral deployment intent, VPS
  composition, and aggregate acceptance are implemented; this does not claim a
  live production deployment

They become user-visible when the subprojects below consume them.

## 🔜 Next

The nearest planned subprojects, in dependency order:

- **Control plane authority** (`SP-CONTROL-PLANE-AUTHORITY`) — establish the
  service authority, lineage, and visibility needed by managed workflows.
- **Managed data environments** (`SP-DATA-ENVIRONMENTS`) — after control plane
  authority is accepted, request an empty, masked-copy, or restored database
  environment as a managed flow instead of through hand-run commands.

## 🎯 Target state

Direction, in intended order — each depends on the previous layers:

1. **Control plane authority + environment requests** — a service that owns instances, not just a CLI
2. **Platform access (RBAC)** — roles and identity for teams, not a single operator
3. **Delivery automation** — complete the CI-driven build/publish/deploy flow
4. **Production governance, resource lifecycle, data recovery** — the operational disciplines around real customer data
5. **Operations UI** — a web surface once the flows beneath it are stable,
   including the guided manifest wizard's web form

## Out of scope (for now)

- Replacing Odoo's own tooling (odoo-bin, module scaffolding)
- Managing Odoo application-level configuration beyond deployment concerns
- Multi-cloud abstraction beyond the deployment-spec boundary

## How this page is maintained

Every tier maps to `status` fields in the portfolio (`achieved`, `proposed`,
`decided`). When a subproject lands, it moves from *Next*/*Target state* into
*Working today* here, in the same PR that archives its change.
