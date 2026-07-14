# SP-1 — ImageRegistryProvider

> **Historical brief (superseded).** Preserved for SP-era design lineage. Use
> [`portfolio.json`](portfolio.json) for current status, evidence, dependencies, and handoffs.

**Layer:** Ports & adapters · **Status:** DONE — the image registry capability is delivered through
the GHCR adapter. Delivery fabrication and promotion remain owned by
`SP-DELIVERY-AUTOMATION`, not SP-1. **SDD change:** delivered under the archived
`openspec/changes/archive/2026-07-09-sp1` / `sp1-a` / `sp1-b` changes; the open
`platform-image-registry-provider` change tracks the remaining doc-tightening work only.

## Purpose
This sub-project introduces the `ImageRegistryProvider` port: the second external concern
(after `SourceProvider`) to be extracted as a pluggable port with interchangeable adapters.
It lets the control plane **publish** fabricated Odoo layer images and **pull** them by
**digest**, so an instance can be deployed from a pre-built, digest-pinned artifact instead of
being materialized from source at deploy time.

This realizes the **pre-built Docker image ("server instance", Model B)** half of the vision
(§1, §4): where a dev instance is *editable source + a database*, a server instance is a
*digest-pinned image* pulled from a registry the control plane never hosts itself. It extends
the Phase 1 image factory — which already publishes parameterized base images to GHCR — from a
one-off build step into a first-class port the orchestrator can drive against any registry.

## Actor(s) served
Primarily **DevOps (operations)** and **control-plane users** (§4 actors 2 and 3). It unblocks
the CD tail of the flow: after CI passes, the fabricated image is published by digest and can
later be pulled for a PROD/QA server instance. It is a foundation port — usable from the CLI
before the server exists (§7).

## Port & adapters
New `Protocol` port `ImageRegistryProvider`, mirroring the `SourceProvider` / `BackendProvider`
shape (interface only in core, adapters in a sibling package, lazy annotations, `runtime_checkable`):

- `publish(ref: ImageRef) -> ImageDigestRef` — push an already-built local image and return its canonical immutable digest.
- `pull(digest: ImageDigestRef) -> LocalImageRef` — fetch a digest into the local daemon and return a local handle.
- `resolve_digest(ref: ImageRef) -> ImageDigestRef` — resolve a supported image reference to a canonical digest.
- `exists(digest: ImageDigestRef) -> bool` — check presence without transferring layers.

These signatures are the implemented contract; the port does **not** keep legacy
`resolve()` / `validate()` bridges. The shape follows the "verbs return
references/handles, never data blobs" convention of the existing ports.

**Delivered adapter (one provider at init, §Principle 3):** GHCR is the delivered adapter. The
global one-provider-at-init decision (DP) is decided; GitLab Registry, AWS ECR, and DockerHub
remain future adapter candidates.

## What it reuses (does NOT build)
- The **Phase 1 image factory** and its digest-pinning discipline — this port wraps publication,
  it does not re-implement image building.
- The **registry service itself** (GHCR/ECR/etc.) — authentication, storage, and layer dedup are
  the registry's job. Reuses cloud secret managers for registry credentials.
- Docker/OCI layer transport — the adapter shells out to the registry's native client/API.

## Pointers, not copies
Stores **image digests** (immutable content references) and registry coordinates only. The
control plane never stores image layers or tarballs — it is not a data lake (§Principle 4).
`project.lock` already models this pointer-only discipline for sources; digests extend it to images.

## Scope
- Define the `ImageRegistryProvider` port in `odoo_forge.ports`.
- One concrete GHCR adapter package (`odoo_forge_registry`) selected at init.
- `publish` / `pull` / `resolve_digest` / `exists` against that adapter.
- A **6th import-linter contract** forbidding `odoo_forge` from importing the new adapter package,
  and adding the adapter to `root_packages`. Before SP-1 there were **5 contracts** in
  `[tool.importlinter]`: 1 generic external-import ban + 1 CLI ban + 3 per-adapter-package bans
  (`odoo_forge_git`, `odoo_forge_workspace`, `odoo_forge_docker`); each new adapter package adds
  one per-package ban, so SP-1 brought the total to **6** (the `odoo_forge_registry` ban now
  exists in `pyproject.toml`).
- CLI surface to publish/pull by digest (foundation-level, pre-server).

## Non-goals
- No multi-registry fan-out at runtime (one adapter per init, §Principle 3).
- No image *building* changes (owned by the Phase 1 factory).
- No control-plane API/registry state (that is SP-4).
- Clarification: SP-1 is **unrelated** to the deprecated **`PublishedLayer` source-resolution**
  (the original "Slice 4a `registry://`" idea, a `SourceProvider`/artifact concern — see the
  roadmap §8 Deprecations). SP-1 is a **container-image registry** port and does **not** resolve
  `PublishedLayer` or touch source resolution; the enterprise-fork need is already a `GitLayer`.

## Dependencies
Foundation only — **Phase 1 (image factory)** and the existing ports/import-linter conventions.
Independent of SP-2/SP-3. Upstream of SP-4 and SP-6 (§6, §7).

## Success criteria
- `ImageRegistryProvider` conformance test passes (`isinstance` + `inspect.signature`), mirroring
  the backend-port conformance pattern.
- Core stays pure: the new adapter package is covered by its own import-linter forbidden contract;
  the purity gate is green.
- Publish→resolve→pull round-trips a digest against the chosen adapter (integration-tested).
- Strict TDD: tests precede implementation; core logic is pure, the adapter is a dumb shell over
  the registry client.

## Open decisions
- Digest format / multi-arch manifest handling surfaced through `ImageDigest`.
- Whether `pull` targets a local docker daemon or a remote backend directly (interaction with SP-3).
