# Proposal: First Pipeline Adapter — GitHub Actions

## Intent

The provider-neutral `PipelineProvider` port (PORT-PIPELINE) is archived but has
no concrete adapter, so the platform cannot actually trigger or read any CI run.
This change delivers ADAPTER-PIPELINE-GITHUB (gap G0): the first concrete
`PipelineProvider`, backed by GitHub Actions. GitHub Actions is chosen as the
first CI engine (DPROV-CI) for coherence with the already-delivered GitHub
ecosystem (GHCR image registry). Success = a GitHub Actions provider that
structurally conforms to the port and maps trigger/status/logs onto Actions
concepts, with hermetic tests.

## Scope

### In Scope
- New adapter package `src/odoo_forge_pipeline_github/` (`provider.py`,
  `__init__.py`) implementing `PipelineProvider`.
- Map `trigger(spec)` → workflow_dispatch, `status(ref)` → workflow run state
  (into neutral `PipelineRunState`), `logs(ref)` → run logs.
- Structural conformance proof (`isinstance` against `runtime_checkable`
  Protocol), mirroring the port's pipeline-provider scenarios.
- Packaging wiring in `pyproject.toml`: `packages`, `root_packages`, and a
  forbidden import-linter contract (core MUST NOT import the adapter), mirroring
  `odoo_forge_registry` (GHCR).
- External I/O behind an injectable transport/HTTP-client seam so tests stay
  hermetic (no live network).

### Out of Scope
- Method-level mapping detail and transport seam design (deferred to design).
- GitLab CI adapter (ADAPTER-PIPELINE-GITLAB stays deferred).
- Flow orchestration (build → pre-prod DB gate → CD) — pure-domain, later work.
- Any change to the port, neutral types, or `odoo_forge` core.
- `port-identity` files (file-disjoint change).

## Capabilities

### New Capabilities
- `github-actions-pipeline-adapter`: concrete GitHub Actions implementation of
  the `PipelineProvider` port, its neutral-state mapping, seam boundary, and
  packaging/import-linter isolation.

### Modified Capabilities
- None. `pipeline-provider` port contract is unchanged.

## Approach

Add an isolated adapter package that depends only on the port + neutral types
(same layering as GHCR). The provider takes an injected transport at
construction; real GitHub REST/dispatch calls live behind that seam so unit
tests use a fake transport. Enforce isolation via a new forbidden import-linter
contract and register the package in build/root-package lists.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_pipeline_github/` | New | Adapter package + provider |
| `pyproject.toml` | Modified | packages, root_packages, forbidden contract |
| `tests/` | New | Conformance + mapping tests (hermetic) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Adapter leaks Actions vocabulary into neutral results | Med | Return only neutral types; assert in tests |
| Hidden network calls in tests | Low | Mandatory injected transport seam |
| Actions run-state → neutral state mapping gaps | Med | Enumerate all `PipelineRunState` mappings in design/tests |

## Rollback Plan

Revert the branch: delete `src/odoo_forge_pipeline_github/` and its tests, and
undo the `pyproject.toml` additions. Core and port are untouched, so no data or
contract migration is involved.

## Dependencies

- PORT-PIPELINE (archived) — provides the port and neutral types.
- GHCR adapter (`odoo_forge_registry`) — packaging/isolation precedent.

## Success Criteria

- [ ] `isinstance(GitHubActionsPipelineProvider(...), PipelineProvider)` passes.
- [ ] trigger/status/logs round-trip against a fake transport; results are
      provider-neutral types only.
- [ ] Import-linter forbids core importing the adapter; check passes.
- [ ] Full test suite (`uv run pytest`) green with no network access.

## Delivery Note

Estimated size: small-to-medium, single PR (one new package + packaging + tests,
comfortably under the 400-line review budget). No PR chaining anticipated.

## Proposal Assumptions (auto mode — no interactive round)

- Public method name assumed `GitHubActionsPipelineProvider`; exact naming/method
  signatures left to design.
- Transport seam realized as a constructor-injected HTTP client abstraction.
- Auth/token handling delegated to the transport; not designed here.
