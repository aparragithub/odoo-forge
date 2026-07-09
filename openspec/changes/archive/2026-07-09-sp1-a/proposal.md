# Proposal: SP1-A — Immutable Image Identity Foundation

## Proposal question round

Finalize requested. Proposal assumes GHCR-first scope, fail-fast/operator-readable diagnostics, and defers real `pull()` behavior to `sp1-b`.

## Intent

Reduce ambiguity around immutable image identity by adding a first registry foundation that resolves and validates GHCR-backed image digests without changing runtime execution, backend planning, or `project.lock` persistence.

## Scope

### In Scope
- Add the `ImageRegistryProvider` port and a first GHCR-focused adapter for digest resolve/validate foundations.
- Add a first CLI surface for digest resolve/validate with clean, operator-readable failure output.
- Fail fast on auth, not-found, and malformed-reference cases; prioritize GHCR auth diagnostics.

### Out of Scope
- Real image `pull()` behavior and runtime/backend consumption of digests (`sp1-b`).
- Multi-registry support, backend/control-plane integration, and `project.lock` changes.

## Capabilities

### New Capabilities
- `image-registry-provider`: Port, GHCR-first adapter, and first CLI commands for resolving and validating immutable image digests.

### Modified Capabilities
- None.

## Approach

Follow the existing hexagonal pattern: keep the port in `odoo_forge`, implement a dumb registry adapter in a sibling package, wire it through `src/odoo_forge_cli/main.py`, and reuse current GHCR/image-factory conventions instead of inventing new registry rules.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/ports/image_registry_provider.py` | New | Registry port contract for immutable image identity operations |
| `src/odoo_forge_registry/` | New | GHCR-first adapter and typed registry error mapping |
| `src/odoo_forge_cli/main.py` | Modified | First digest resolve/validate CLI commands |
| `pyproject.toml` | Modified | New package wiring and sixth import-linter purity contract |
| `tests/ports/`, `tests/adapters/`, `tests/cli/` | Modified | Port conformance, adapter, and resilient-boundary coverage |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| GHCR auth failures are opaque | Med | Normalize auth errors into explicit operator diagnostics |
| Slice drifts into runtime/pull behavior | Med | Keep `pull()` semantics deferred to `sp1-b` and exclude backend changes |
| GHCR details leak into core | Low | Enforce sibling adapter package + import-linter guard |

## Rollback Plan

Revert the new CLI commands, registry adapter package, port wiring, tests, and import-linter additions. No persisted schema or runtime state changes are introduced in this slice.

## Dependencies

- Existing GHCR publishing conventions in `.github/workflows/build-images.yml` and `factory/`.

## Success Criteria

- [ ] Operators can resolve a mutable GHCR image reference to an immutable digest from the CLI.
- [ ] Validation/auth failures exit fast with single-cause, operator-readable diagnostics.
- [ ] Core purity remains enforced and no backend or `project.lock` behavior changes in `sp1-a`.
