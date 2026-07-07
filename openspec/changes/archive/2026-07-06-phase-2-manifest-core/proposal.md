# Proposal: Phase 2 Slice 1 — Manifest Core (schema-validated)

## Intent

Deliver the pure manifest/lockfile domain for `odoo-forge`, and close three schema
gaps the approved design assumed were resolved. The schema is the deliverable; if it
cannot faithfully express the real `odoo-idp` project (fire test), it is wrong. Fixing
the gaps now avoids a schema revision after later slices depend on it. Stays PURE:
no git, docker, or network — the three fixes add only declaration, never infrastructure.

## Scope

### In Scope
- Pydantic v2 schemas (`project.yaml` manifest + `project.lock` lockfile) per platform spec §2.3.
- The three resolved schema decisions below.
- Onion composition (order + coherence) and pure `detect_drift(manifest, lock, materialized)`.
- `SourceProvider` port (interface only), thin `forge validate` CLI, day-1 import-linter gate.
- Fire-test fixture expressing `odoo-idp` (incl. the `odoo-argentina-ee` edition case).

### Out of Scope
- Pin resolution / git `SourceProvider` adapter / `forge lock` (Slice 2).
- Workspace projection, layer→mount-root mapping, unlock (Slice 3).
- Local Docker backend (Slice 4). HTTP/registry client libs (not called yet).

## Resolved schema decisions (one approach each)

1. **Core/community pin — add a first-class `core` field.** `Manifest.core: CoreLayer`
   with `type: Literal["core"]`, `url: str = "https://github.com/odoo/odoo.git"`,
   `ref: str | None = None` (defaults to the `odoo_version` branch at compose time).
   *Why:* exactly one always-present base layer deserves a required field, not a freeform
   `layers` entry; it carries only intent (SHA resolves in the lockfile, Slice 2), so it
   never duplicates `factory/versions.yaml`.

2. **Per-repo edition gating — add `requires_edition`.** Optional
   `requires_edition: Literal["enterprise"] | None = None` on `GitRepo` and on each layer
   type. Coherence rule: `edition == "community"` MUST NOT include any repo/layer requiring
   enterprise. *Why:* edition access is a property of the artifact, not the layer name —
   this catches `odoo-argentina-ee` nested inside the `localization` layer.

3. **Explicit discriminated union.** Add `type: Literal[...]` to each member and use
   `Annotated[PublishedLayer | GitLayer, Field(discriminator="type")]`. *Why:* deterministic
   parsing with single-member error messages; smart-mode reports ambiguous errors against
   both members, breaking the "clear errors on malformed input" criterion.

**Spec clarifications:** manifest hash = sha256 over the canonicalized in-memory model
(`model_dump_json`, sorted keys), never raw file bytes — keeps hashing in the pure core.
import-linter keeps `odoo_forge` free of infra/CLI imports.

## Capabilities

### New Capabilities
- `manifest-schema`: `project.yaml`/`project.lock` Pydantic models incl. `core`, `requires_edition`, discriminated `Layer`.
- `onion-composition`: layer ordering + coherence (edition, override-target, client-last).
- `drift-detection`: pure three-input drift function + `MaterializedState` model.
- `forge-validate-cli`: thin `forge validate` command delegating to the core.

### Modified Capabilities
- None (new product surface; no existing `openspec/specs/`).

## Approach

Full §2.3 schema (Approach 1) with the three amendments, TDD domain-first, import-linter
as a blocking CI gate from commit one. CLI orchestrates and presents; all logic in the core.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/manifest/` | New | schema, lockfile, composition, drift, state, errors |
| `src/odoo_forge/ports/source_provider.py` | New | port interface only |
| `src/odoo_forge_cli/main.py` | New | `forge validate` |
| `importlinter.ini`, `pyproject.toml` | New | purity gate + uv deps |
| `tests/manifest/`, `tests/fixtures/` | New | domain tests + odoo-idp fire test |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `core` field over-fits odoo/odoo | Low | `url` overridable; only intent stored |
| `requires_edition` too narrow later | Low | field can widen to enum without breaking data |
| Hash impurity via disk re-read | Med | spec mandates in-memory canonicalization + import-linter |

## Rollback Plan

Pure additive slice in a new `src/` tree; revert the branch. No Phase 1 (`factory/`) or
runtime state touched — nothing to migrate back.

## Dependencies

- Python 3.12+, uv, pydantic v2, pyyaml, typer; dev: pytest, import-linter.
- Read access to `/home/aparra/Development/wk/odoo-idp` for the fire-test fixture.

## Success Criteria

- [ ] `forge validate` parses valid `project.yaml`, reports clear single-member errors on malformed input, and reports manifest↔lock drift when a lockfile exists.
- [ ] Fire-test fixture expressing `odoo-idp` parses and composes cleanly, including `core` (odoo/odoo@19.0) and `odoo-argentina-ee` marked `requires_edition: enterprise` inside `localization`.
- [ ] Composition rejects a `community` manifest that includes any enterprise-requiring repo/layer.
- [ ] import-linter passes as a blocking CI job; core has zero docker/git/boto3/k8s/typer imports.
- [ ] Manifest hash computed from the canonicalized in-memory model; full domain suite green.
