## Exploration: SP1-B — Real Image Pull and Runtime Digest Consumption

### Current State
SP1-A stops at CLI-only digest resolution/validation. `image-resolve` and `image-validate` in `src/odoo_forge_cli/main.py` call the GHCR registry adapter and return canonical digest refs, but nothing persists or consumes them afterward. Runtime still flows through `forge run` → workspace scan/materialize → `plan_backend(...)` → `DockerBackendProvider.run(...)`, and `src/odoo_forge/backend/plan.py` hardcodes the Odoo image as `odoo-forge-odoo:{odoo_version}`. There is no explicit `docker pull` path anywhere in `src/`, and `project.lock` still models only git-layer pins while published-layer registry resolution remains a separate `phase-2-slice-4a-registry-resolution` track.

### Affected Areas
- `src/odoo_forge_cli/main.py` — owns the registry/backend composition roots and all current entrypoints for digest resolution and runtime execution.
- `src/odoo_forge/backend/plan.py` — current seam where the runtime Odoo image is selected and where digest-aware planning would have to land.
- `src/odoo_forge_docker/provider.py` — current Docker subprocess boundary; `run()` creates containers but never performs an explicit pull.
- `src/odoo_forge/ports/backend_provider.py` — may need a widened contract if pull becomes first-class instead of remaining implicit inside `run()`.
- `src/odoo_forge/manifest/lockfile.py` — only affected if `sp1-b` chooses persisted digest consumption; current schema has no image-digest slot.
- `openspec/changes/phase-2-slice-4a-registry-resolution/explore.md` — adjacent but separate work on `PublishedLayer`/`build_lock`; should remain out of `sp1-b`.

### Approaches
1. **Ephemeral backend seam** — Thread a canonical digest ref from CLI/runtime input into backend planning and add explicit local-Docker pull behavior before container start.
   - Pros: Reuses the SP1-A registry foundation; stays bounded to runtime/backend consumption; avoids `project.lock` schema churn and overlap with `phase-2-slice-4a-registry-resolution`.
   - Cons: Digest is not persisted for replay; proposal must choose the runtime input shape explicitly.
   - Effort: Medium

2. **Persisted digest flow** — Extend manifest/lockfile state to carry resolved image digests and make backend execution consume that stored value.
   - Pros: Stronger reproducibility and a single stored source of truth.
   - Cons: Expands blast radius into manifest/lockfile schema, drift/validate flows, and conceptually collides with the separate published-layer registry-resolution work.
   - Effort: High

### Recommendation
Use **Ephemeral backend seam**. The smallest coherent `sp1-b` slice is to accept/use a canonical digest ref at the CLI boundary, make `plan_backend` choose that digest-backed image instead of the tag template when provided, and teach the Docker adapter to perform an explicit local-daemon pull before `docker run`. That delivers the deferred runtime/backend consumption without reopening `project.lock` or the deprecated `PublishedLayer` path.

### Risks
- If the proposal does not pin the input shape, `sp1-b` can sprawl into manifest/lock persistence work.
- Pull semantics are still ambiguous outside the local Docker backend; proposal should scope them to the local daemon only.
- Any `BackendPlan` or `BackendProvider` contract change will touch existing backend tests and can exceed a single review slice if combined with persistence changes.

### Ready for Proposal
Yes — tell the user `sp1-b` is ready if the proposal explicitly keeps `PublishedLayer` / `registry://` resolution and `project.lock` schema changes out of scope, and chooses a bounded local-Docker digest consumption path.
