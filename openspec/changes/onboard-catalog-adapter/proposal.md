# Proposal: Catalog-Driven Onboarding (`forge onboard <cliente>`)

## Intent

`project_catalog.CatalogIndex` is a fully-designed Protocol with zero concrete
implementations and zero consumers — `ProjectCatalogResolver` is pure, tested,
and unused in production. Meanwhile `forge onboard` already ships but only
covers the local-input slice (`--manifest`): validate + materialize, no
catalog lookup, no instance creation. Devs who want to work on a client's
Odoo system by name alone still have no path to get there. This change gives
`CatalogIndex` its first real adapter and wires it into `onboard` so "ask for
a client by name" becomes possible, without touching the already-shipped
local-manifest path.

## Scope

### In Scope
- Concrete `CatalogIndex` adapter (new top-level `src/odoo_forge_catalog/`
  package) reading a declarative catalog source, returning `CatalogRecord`s
  via `find_matches(request)`. Exact source format is an adapter-internal
  decision (see Risks).
- Composition-root factory `_make_catalog_index()` in
  `src/odoo_forge_cli/_composition.py`, following the existing
  `_make_workspace_provider` / `_make_backend_provider` shape.
- **Dual-mode dispatch on the existing `onboard` command** (verbatim user
  decision): `forge onboard --manifest <path>` keeps today's shipped
  behavior unchanged — local validate + materialize only, no backend
  creation. `forge onboard <cliente>` (new positional arg) activates the
  catalog-driven path: resolve via `ProjectCatalogResolver` → materialize
  repos (reusing `project_workspace`/`plan_projection`) → create the
  instance (reusing `plan_backend` + `DockerBackendProvider.run`). On
  resolver failure, render a single `error:` line distinguishing
  `catalog-not-found` / `ambiguous-resolution` / `invalid-catalog`, nonzero
  exit. The two modes are mutually exclusive dispatch branches on the same
  command — not merged behavior.
- Package registration for the new adapter package in all three required
  `pyproject.toml` spots: `[tool.hatch.build.targets.wheel].packages`,
  `[tool.importlinter].root_packages`, and its own forbidden-import
  contract (core -/-> adapter).
- Tests: `tests/adapters/test_catalog_index_provider.py` (faked catalog
  source, match/no-match/ambiguous-passthrough cases) and CLI-level coverage
  extending `tests/cli/` conventions (fake `CatalogIndex` + fake
  `BackendProvider`, asserting rendered output/exit code, not call order).

### Out of Scope (inherited from `.scratch/dev-onboarding/spec.md`)
- Control plane, server, API, auth, shared persistent state (ADR-0001).
- Cloning an existing client instance and anonymized DB (future capability).
- Seeded DB from declarative seed.
- Remote backends (EC2, VPS, Kubernetes, Fargate) and honoring a non-local
  `target_default`.
- Functional/Devops actor journeys (shared test instances, CI/CD, monitoring).
- Non-CLI interfaces.
- Post-onboarding dev push workflow.
- Modifying `ProjectCatalogResolver` or the `run`/`project` command flows —
  they are reused as-is, unchanged.

## Capabilities

### New Capabilities
- `catalog-index-adapter`: concrete `CatalogIndex` implementation backed by a
  declarative catalog source, plus its composition-root wiring.

### Modified Capabilities
- None at the requirements level for `project-catalog-resolution` (resolver
  behavior is unchanged; this only gives it a real caller).
- `manifest` capability's `onboard` command behavior gains a new dispatch
  branch — treated as an addition (new positional-arg mode), not a change to
  existing `--manifest` requirements.

## Approach

Follow the reference flows already proven in the codebase: reuse `run`'s
manifest→workspace→plan_backend→provider.run pipeline and `project`'s
projection/materialization pipeline verbatim. The only new code is (1) the
adapter translating a catalog source into `CatalogRecord`s and (2) a
dispatch branch in the `onboard` command that, given a positional client
identifier instead of `--manifest`, calls `ProjectCatalogResolver.resolve()`
first and then feeds the resolved `manifest_ref`/`source_context` into the
existing materialize+backend pipeline. No core logic changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_catalog/` | New | Concrete `CatalogIndex` adapter package |
| `src/odoo_forge_cli/_composition.py` | Modified | Add `_make_catalog_index()` factory |
| `src/odoo_forge_cli/commands/manifest.py` | Modified | Add catalog-driven dispatch branch to `onboard` |
| `pyproject.toml` | Modified | Register new adapter package (3 spots) |
| `tests/adapters/test_catalog_index_provider.py` | New | Adapter contract tests |
| `tests/cli/` | Modified | Extend `onboard` coverage for catalog-driven mode |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Catalog source format undecided (YAML/JSON/other) | Med | Defer to sdd-design; keep adapter boundary so format choice is isolated and non-breaking to `CatalogIndex` contract |
| ADR-0001 sequencing: `data_policy_default`/`target_default` are transported but unused this slice | Low | Explicitly documented as pass-through-only fields per original spec; effective target stays local-only, no seed/clone logic added |
| Dual-mode dispatch ambiguity (mixing `--manifest` and positional arg) | Med | sdd-spec must define explicit mutual-exclusivity validation and its error message |
| Catalog adapter drifting into resolver/backend logic | Low | Adapter contract is `find_matches` only; ambiguity resolution stays in the resolver per existing tests |

## Rollback Plan

The change is additive: a new adapter package, one new composition factory,
and one new dispatch branch gated on positional-arg presence. Revert by
removing the new package, the factory, the dispatch branch, and the
`pyproject.toml` registrations. The existing `--manifest` mode of `onboard`
is untouched code path and requires no rollback handling of its own.

## Dependencies

- None external. Depends on already-merged `ProjectCatalogResolver` and
  `CatalogIndex` Protocol, and already-shipped `onboard --manifest` slice.

## Success Criteria

- [ ] `forge onboard <cliente>` resolves via a real `CatalogIndex` adapter,
      materializes repos, and creates a running instance end-to-end.
- [ ] `forge onboard --manifest <path>` behavior is verified unchanged (no
      regression in existing tests).
- [ ] All three failure classes (`catalog-not-found`, `ambiguous-resolution`,
      `invalid-catalog`) render distinguishable `error:` lines with nonzero
      exit, with no orphaned instance on backend failure.
- [ ] New adapter package passes import-linter contracts (core independent
      of adapter).
