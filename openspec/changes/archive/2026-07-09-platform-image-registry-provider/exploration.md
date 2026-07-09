## Exploration: platform-image-registry-provider

### Current State
The repo already implements two archived foundations that cover part of SP-1. `sp1-a` added a GHCR-first `ImageRegistryProvider` seam, but the current port is still the narrower pre-platform contract: `resolve(ref)` and `validate(ref)` in `src/odoo_forge/ports/image_registry_provider.py`, backed by `src/odoo_forge_registry/provider.py` via `docker buildx imagetools inspect`, and exposed only through `forge image-resolve` / `forge image-validate` in `src/odoo_forge_cli/main.py`. `sp1-b` already consumes digest-backed images at runtime: `forge run --odoo-image-ref` normalizes a canonical digest, `src/odoo_forge/backend/plan.py` threads it into `BackendPlan.odoo.image`, and `src/odoo_forge_docker/provider.py` performs an explicit `docker pull` before container start. Phase 1 already publishes GHCR images by digest in `.github/workflows/build-images.yml`, and `pyproject.toml` already includes the 6th import-linter contract for `odoo_forge_registry`. What is still missing is the actual platform SP-1 contract from `docs/specs/platform/SP-1-image-registry-provider.md`: a platform port shaped around `publish`, `pull`, `resolve_digest`, and `exists`, plus CLI and adapter behavior aligned to that port. The deprecated `PublishedLayer` path is still present in manifest code, but the roadmap explicitly marks it as unrelated to this change.

### Affected Areas
- `docs/specs/platform/SP-1-image-registry-provider.md` — source-of-truth scope and final port intent for the new change.
- `docs/specs/2026-07-08-platform-roadmap.md` — confirms SP-1 is the platform image-registry port and explicitly deprecates `PublishedLayer` as unrelated.
- `openspec/specs/image-registry-provider/spec.md` — current main spec still reflects the narrower `sp1-a` resolve/validate-only scope and will need a platform-aligned delta.
- `src/odoo_forge/ports/image_registry_provider.py` — current protocol is structurally incomplete for platform SP-1.
- `src/odoo_forge/image_registry/reference.py` — current helper is GHCR-only and shaped around tag/digest validation, not the broader platform operations.
- `src/odoo_forge/image_registry/errors.py` — current error family is inspect-oriented and may need expansion/reframing for publish/pull/exists flows.
- `src/odoo_forge_registry/provider.py` — current adapter only inspects remote manifests; it does not publish, pull, or perform non-transfer existence checks.
- `src/odoo_forge_cli/main.py` — currently exposes `image-resolve` / `image-validate` plus runtime digest override, but no platform-level publish/pull CLI.
- `.github/workflows/build-images.yml` and `factory/build.sh` — existing Phase 1 publication flow that SP-1 must wrap/reuse rather than re-implement.
- `src/odoo_forge/backend/plan.py` and `src/odoo_forge_docker/provider.py` — already-completed runtime digest consumption seam that the new port must complement, not duplicate.
- `src/odoo_forge/manifest/schema.py`, `src/odoo_forge/manifest/locking.py`, `src/odoo_forge/manifest/projection.py`, `src/odoo_forge/manifest/composition.py` — still contain deprecated `PublishedLayer` references that must stay out of SP-1 scope.
- `tests/ports/test_image_registry_provider.py`, `tests/adapters/test_registry_provider.py`, `tests/cli/test_image_registry.py` — existing SP1-A tests that will need contract and CLI evolution.

### Approaches
1. **Evolve the existing GHCR-first registry foundation** — Treat `sp1-a` and `sp1-b` as partial SP-1 delivery, then expand the current port/adapter/CLI into the platform contract.
   - Pros: Reuses the current hexagonal seam, import-linter boundary, GHCR adapter package, and runtime digest consumption already delivered in `sp1-b`; best fit with the platform roadmap and Phase 1 GHCR pipeline.
   - Cons: Requires a breaking contract redesign from `resolve`/`validate` to the platform verbs; proposal must carefully separate generic registry-port semantics from Docker-backend-local runtime pull behavior.
   - Effort: Medium

2. **Add a second platform registry abstraction beside the current one** — Keep the current inspect-only `ImageRegistryProvider` behavior and introduce a new port/package for platform SP-1.
   - Pros: Lower short-term disruption to the current CLI/tests.
   - Cons: Duplicates the same concern under two abstractions, conflicts with the platform document as source of truth, and leaves the repo carrying obsolete pre-platform semantics longer.
   - Effort: High

### Recommendation
Use **Evolve the existing GHCR-first registry foundation**. The repo already has the right architectural seam; what is wrong is the CURRENT CONTRACT, not the existence of the seam itself. The next proposal should redefine `ImageRegistryProvider` around the platform verbs, keep GHCR as the first concrete adapter, explicitly reuse the existing Phase 1 publication pipeline, and treat `sp1-b`'s runtime digest consumption as an already-finished downstream consumer. The proposal should also forecast chained delivery, because contract changes plus CLI/adapter/test updates are likely to exceed a comfortable single-PR review slice.

### Risks
- The platform doc names `publish(image_ref, source)` and `pull(digest) -> LocalImageRef`, but the concrete value types and ownership boundaries are not finalized anywhere in code yet.
- `sp1-b` already performs a Docker-local explicit pull inside `DockerBackendProvider.run()`, so the proposal must avoid duplicating or fighting that responsibility.
- The current OpenSpec main spec for `image-registry-provider` is narrower than the platform source of truth, so proposal/spec work must correct that drift explicitly.
- `PublishedLayer` still exists in manifest code; if the change tries to remove or redesign it now, SP-1 will sprawl into deprecated source-resolution cleanup.
- Review-size risk is real; this work should be planned as chained slices under the existing 400-line review budget.

### Ready for Proposal
Yes — tell the user the change is ready if the proposal first freezes the platform port contract, keeps GHCR as the first adapter, treats `sp1-a` and `sp1-b` as already-done foundations, and keeps deprecated `PublishedLayer` cleanup out of scope except as a separate follow-up change.
