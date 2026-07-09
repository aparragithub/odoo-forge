## Exploration: SP-1 — ImageRegistryProvider

### Current State
Phase 1 already publishes multi-arch Odoo CE base images to GHCR through `.github/workflows/build-images.yml`, using push-by-digest, smoke tests before tagging, and `docker buildx imagetools` to assemble multi-arch manifests. The application runtime follows a strict hexagonal pattern: ports live under `src/odoo_forge/ports`, pure use-cases stay in core, concrete adapters live in sibling packages, and `src/odoo_forge_cli/main.py` is the composition root. There is currently no image-registry port in code. `src/odoo_forge/backend/plan.py` hardcodes the runtime image as `odoo-forge-odoo:{odoo_version}`, and `src/odoo_forge/manifest/lockfile.py` models source pins only, not image digests. The platform roadmap explicitly deprecates the old `PublishedLayer` / Slice 4a registry-resolution idea; SP-1 is a container-image registry concern, not source resolution.

### Affected Areas
- `docs/specs/platform/SP-1-image-registry-provider.md` — primary scope definition and open decisions.
- `docs/specs/2026-07-08-platform-roadmap.md` — establishes SP-1 as the image-registry port and deprecates `PublishedLayer` registry resolution.
- `src/odoo_forge/ports/` — new `image_registry_provider.py` should follow the existing Protocol + `runtime_checkable` pattern.
- `src/odoo_forge_cli/main.py` — composition root and likely CLI surface for `publish`, `pull`, `resolve_digest`, and `exists`.
- `pyproject.toml` — must add the new sibling adapter package and a sixth import-linter forbidden contract.
- `src/odoo_forge_registry/` (new sibling adapter package) — likely first concrete adapter package for GHCR or generic OCI registry access.
- `tests/ports/`, `tests/adapters/`, `tests/cli/` — existing port conformance, adapter signature, and resilient-boundary testing patterns should be mirrored.
- `src/odoo_forge/backend/plan.py` — downstream consumer once digest-pinned images are wired into runtime planning; probably not initial SP-1 scope.
- `src/odoo_forge/manifest/lockfile.py` — downstream only if image digests later become part of reproducible state.
- `.github/workflows/build-images.yml`, `factory/build.sh`, `factory/README.md` — existing digest, tag, and GHCR conventions the adapter should reuse rather than reinvent.

### Approaches
1. **Standalone registry foundation** — add `ImageRegistryProvider`, a first adapter, and CLI commands for registry operations without changing backend planning or lockfile shape yet.
   - Pros: Matches the SP-1 brief, preserves current seams, keeps scope bounded, and fits the repo's proven port/adapter/TDD pattern.
   - Cons: The pre-built image model is not yet consumed by `forge run` or any control-plane flow.
   - Effort: Medium

2. **Registry plus immediate runtime integration** — add the port and also thread digest-pinned images into backend planning and instance flows now.
   - Pros: Exercises the pre-built image model sooner and reduces later integration work.
   - Cons: Pulls SP-1 into SP-3/SP-4 territory, forces unresolved decisions about image-reference modeling and pull targets, and increases blast radius significantly.
   - Effort: High

### Recommendation
Use **Standalone registry foundation**. SP-1 should establish the port, first adapter, CLI composition, import-linter guard, and tests, while explicitly deferring backend/runtime consumption of digests to later platform slices. That keeps the change aligned with the roadmap, avoids coupling to the deprecated `PublishedLayer` path, and protects scope.

### Risks
- `pull(digest)` semantics are still open: local Docker daemon vs target-reachable form for future remote backends.
- The current local-backend image selection (`odoo-forge-odoo:{odoo_version}`) does not line up with Phase 1 GHCR publishing, so later runtime integration will need a separate image-selection design.
- A GHCR-specific implementation that skips the existing subprocess-adapter convention could make future registry swaps harder.
- Forcing digests into `project.lock` now would widen scope into schema evolution before a real consumer exists.

### Ready for Proposal
Yes — if the proposal explicitly frames SP-1 as the **ImageRegistryProvider foundation slice** and not as the deprecated Slice 4a registry-resolution idea. The proposal should also ask for confirmation of the first adapter choice (GHCR is the natural default) and the intended `pull(digest)` target semantics.
