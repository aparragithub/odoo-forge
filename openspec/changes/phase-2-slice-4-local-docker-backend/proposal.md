# Proposal: Phase 2 Slice 4b — Local Docker Backend

## Intent

Phase 2's exit criterion is "one command, working Odoo". Slice 3 projects the
manifest onto disk (`MaterializedState`) but nothing runs it. This slice adds the
first backend (`local`, design §2.4) so a materialized workspace becomes a live,
introspectable Odoo instance via Docker. It also closes an unstated gap:
`factory/entrypoint.sh:143-159` hard-requires a reachable Postgres that nothing
currently provisions.

## Scope

### In Scope
- New `BackendProvider` Protocol port in `src/odoo_forge/ports/backend_provider.py`.
- New sibling adapter package shelling out to the `docker` CLI via `subprocess`
  (argv-list, no `shell=True`) — mirrors `odoo_forge_git`/`odoo_forge_workspace`.
- Pure core planner: compute container/network/mount/env plan from manifest +
  Slice-3 `MaterializedState` as pure functions; `odoo_forge` stays import-pure.
- Backend ops: `run` (create_instance), `status`, `stop`, `logs`, `exec`.
- Own-Postgres provisioning: backend creates a Postgres container + docker network
  and wires the Odoo container to it (`DB_HOST` etc.).
- Label-based state: `status()` introspects Docker (`docker inspect`/labels); no
  parallel running-instance registry (design §6.2).
- 5th import-linter contract forbidding `odoo_forge -> <new backend adapter package>`.
- CLI commands via composition root (`_make_backend_provider()` in `main.py`).
- Update roadmap §Slice 4 note to record the 4a/4b split.

### Out of Scope
- **4a registry resolution**: `PublishedLayer`/`registry://` lock resolution
  (`locking.py:27-29`) — deferred to a future slice.
- **backup/restore**: design §5 buckets to Phase 4.
- **Seeding/anonymization** (§4.3, §9.5): note extension point only; no implementation.

## Capabilities

### New Capabilities
- `local-backend`: Docker-backed instance lifecycle (run/status/stop/logs/exec),
  own-Postgres provisioning, pure planner, label-based state introspection.

### Modified Capabilities
- None (no `manifest` requirement changes).

## Approach

Pure core decides, dumb adapter executes (Slice 3 invariant). Core planner turns
manifest + `MaterializedState` into a declarative Docker plan; the subprocess
adapter runs the argv the plan dictates and parses `docker inspect` back into
typed status. Typed error family → single-line error + `Exit(1)`,
stop-on-first-failure, per-OS mount strategy internal to the adapter.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/ports/backend_provider.py` | New | `BackendProvider` Protocol |
| `src/odoo_forge/backend/` (core planner) | New | Pure container/network/mount/env plan |
| `<new backend adapter package>/` | New | docker-CLI subprocess adapter |
| `src/odoo_forge_cli/main.py` | Modified | 5 commands + `_make_backend_provider()` |
| `pyproject.toml` | Modified | 5th import-linter contract |
| `docs/specs/2026-07-06-phase-2-slices-roadmap.md` | Modified | Record 4a/4b split |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `docker run` argv brittleness for complex flags | Med | Pure planner builds argv from typed plan; snapshot-test the argv |
| Postgres/Odoo startup race | Med | Healthcheck-gated readiness (`HEALTHCHECK`, EXPOSE 8069/8072) |
| Orphaned PG container/network on failed `run` | Med | Label-scoped cleanup; stop-on-first-failure with teardown |
| Slice exceeds 400-line PR budget (port+adapter+PG+5 CLI) | High | Feature-branch chain; PR split decided in sdd-tasks |
| Multi-OS mount divergence | Low | Per-OS mount strategy isolated in adapter |

## Rollback Plan

Additive slice. Revert the feature-branch chain; no `manifest` schema/lock change,
so Slices 1-3 are unaffected. `docker`/`httpx`/`requests` already forbidden from
core, so reverting the adapter leaves core import-clean.

## Dependencies

- Docker CLI available on host (adapter runtime prerequisite; surfaced via `doctor`).
- Slice 3 `MaterializedState` as planner input.
- `factory/` image (Dockerfile + entrypoint) as the Odoo container base.

## Success Criteria

- [ ] `forge run` produces a reachable Odoo + provisioned Postgres from a materialized workspace.
- [ ] `status`/`stop`/`logs`/`exec` operate against Docker with no parallel registry.
- [ ] `odoo_forge` core stays import-pure; 5th import-linter contract passes.
- [ ] Adapter unit-tested via `subprocess.run` monkeypatch (zero real docker/network).

## Delivery Note

Feature-branch-chain, Strict TDD. Strong chained-PR candidate: port + pure planner +
docker adapter + Postgres provisioning + 5 CLI commands. PR count is deferred to sdd-tasks.
