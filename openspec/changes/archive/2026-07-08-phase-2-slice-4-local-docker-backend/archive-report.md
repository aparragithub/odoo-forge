# Archive Report: Phase 2 Slice 4b — Local Docker Backend

**Change**: phase-2-slice-4-local-docker-backend  
**Status**: ✅ COMPLETE AND ARCHIVED  
**Archived to**: `openspec/changes/archive/2026-07-08-phase-2-slice-4-local-docker-backend/`  
**Date**: 2026-07-08  
**Mode**: Hybrid (Engram + openspec)

---

## Executive Summary

Phase 2 Slice 4b (Local Docker Backend) is fully implemented across 6 chained PRs, verified PASS with all gates green, and now archived. The slice delivers the first `BackendProvider` implementation, turning a Slice-3 `MaterializedState` into a live, introspectable Odoo instance on Docker with its own provisioned Postgres. Pure core planner (port + error family + specs) decoupled from dumb subprocess adapter (docker CLI) and CLI commands, mirroring the proven ports/adapters spine. **Slice 4a (registry resolution for `PublishedLayer`) is deferred as a separate future slice.**

---

## What Shipped (6-PR Chain: PR-1a/1b, PR-2a-i/2a-ii/2b, PR-3a/3b)

### Capabilities Delivered

| Capability | Delivered | Artifacts |
|-----------|-----------|-----------|
| `BackendProvider` Protocol (run/status/stop/logs/exec, no backup/restore) | ✅ PR-1a | `ports/backend_provider.py` |
| Pure backend planner (`plan_backend`, specs, `sanitize_name`) | ✅ PR-1a | `backend/plan.py`, `backend/errors.py` |
| Pure status parser (`parse_status`, `InstanceRef`/`InstanceStatus`/`ExecResult`) | ✅ PR-1b | `backend/status.py` |
| Docker adapter run/rollback (created-only, PG/Odoo readiness gates, injectable clock) | ✅ PR-2a-i/2a-ii | `odoo_forge_docker/provider.py` |
| Docker adapter status/stop/logs/exec + contract conformance | ✅ PR-2b | `odoo_forge_docker/provider.py` (complete) |
| `forge run`/`forge status` CLI + composition root + 5th import-linter contract | ✅ PR-3a | `main.py`, `pyproject.toml` |
| `forge stop`/`forge logs`/`forge exec` CLI + integration marker | ✅ PR-3b | `main.py`, `pyproject.toml` |

### Test & Lint Gates

| Gate | Result | Evidence |
|------|--------|----------|
| **Unit tests** | ✅ **242 passed, 1 deselected** | `uv run pytest -q` (integration skeleton correctly deselected) |
| **Import-linter** | ✅ **5 kept, 0 broken** | `uv run lint-imports` (core remains import-pure; new 5th contract forbids `odoo_forge → odoo_forge_docker`) |

### Specs Merged

| File | Action | Details |
|------|--------|---------|
| `openspec/specs/local-backend/spec.md` | **Created** | New baseline spec capturing all 5 capabilities with scenarios and non-goals. Source: `openspec/changes/phase-2-slice-4-local-docker-backend/specs/local-backend/spec.md` (delta → baseline). |
| `openspec/specs/manifest/spec.md` | Untouched | Manifest spec unchanged (Slice 4 adds no manifest requirements). |

### Artifacts Created

**Baseline spec** `openspec/specs/local-backend/spec.md`:
- `backend-provider-port` Capability (Protocol, 3 scenarios)
- `backend-planner` Capability (pure `plan_backend`, 5 scenarios)
- `postgres-provisioning` Capability (run + readiness gates + named volumes, 1 scenario)
- `label-based-status` Capability (status no-registry, 2 scenarios)
- `forge-backend-cli` Capability (resilient boundary, 5 scenarios + PortConflict supersession + DockerNotAvailable dual-path)
- Non-goals and deferred decisions documented

---

## PR Chain Structure & Key Decisions

### PR-1a: Port, Errors, Pure Planner
- `BackendProvider` Protocol (run/status/stop/logs/exec, final signatures)
- `BackendError` family (DockerUnavailableError, ImageNotFoundError, PostgresReadinessError, ContainerRunError, InstanceNotFoundError, InstanceExistsError)
- Pure planner: `plan_backend`, `sanitize_name`, specs/labels/env
- 2 new files, modified 0 existing → ~280 changed lines (within budget)

### PR-1b: Pure Status Parser
- `InstanceRef`, `InstanceStatus`, `ExecResult` (pydantic)
- Pure `parse_status(json)` with two-stage readiness logic (running-state first, then per-role health)
- 1 new file → ~200 changed lines (within budget)

### PR-2a-i: Docker Adapter argv + Errors
- Package scaffold, pure argv builders, subprocess boundary, error classification, existence checks
- No `run()`, no rollback yet (partial delivery)
- ~390 changed lines (within budget; review-reliability fix for ephemeral ports + `:ro` mounts added)

### PR-2a-ii: Docker Adapter run() + Rollback
- `run()` orchestration, PG/Odoo readiness gates, created-only rollback (critical data-loss guard), injectable clock
- Pre-run existence check (`InstanceExistsError`)
- **Size exception**: 537 changed lines total (34% over 400-line budget)
  - **Root cause**: 14 judgment-day-hardened tests ported verbatim from snapshot (full `run()` ordering, PG/Odoo gates, created-only rollback, reattach-then-fail guard, InstanceExistsError, 3 error-classification variants)
  - **Mitigation**: Flagged to orchestrator; not re-split per explicit boundary instruction
  - **Review coverage**: review-resilience + review-reliability (subprocess boundary, rollback/idempotency, partial-failure)
  - **Additional blocker fixes included**: TimeoutExpired handling + rollback per-step best-effort try/except

### PR-2b: Docker Adapter status/stop/logs/exec + Contract Conformance
- `status()` (docker inspect + label filter)
- `stop()` (containers removed, named PG + filestore volumes preserved)
- `logs(role)` and `exec(argv)` returning ExecResult
- Protocol conformance (isinstance + signature-match via inspect.signature + type-hint comparison)
- Post-review follow-ups: signature-conformance test strengthened to compare type annotations; `stop` partial-instance test added
- ~327 changed lines (under budget)

### PR-3a: forge run/status + Composition Root + 5th Contract
- `_make_backend_provider()` composition root (mirrors `_make_provider()` pattern)
- `forge run [--manifest][--instance]` calling `plan_backend` + `provider.run`
- `forge status [--manifest][--instance]` (never raises for absent instance)
- 5th import-linter contract (forbidden `odoo_forge → odoo_forge_docker`)
- Post-blocker fixes: (BLOCKER) error boundary widened to `(ManifestError, BackendError)` matching `project` pattern; (CRITICAL) `instance` parameter sanitized consistently; edge-case tests added
- ~370 changed lines (under budget)

### PR-3b: forge stop/logs/exec + Integration Marker
- `forge stop [--instance]`
- `forge logs [--instance][--role]`
- `forge exec [--instance] -- ARGV`
- Integration pytest marker + skeleton (deselected by default)
- Post-follow-up fixes: return-type annotation fix, edge-case tests (invalid role, exit-0 passthrough, scan-error parametrization extended), DEBT-2 tracked
- ~378 changed lines (under budget)

---

## Key Design Decisions (Judgment-Day Hardened)

| Decision | Concrete Evidence | Status |
|----------|------------------|--------|
| **Pure planner emits specs; adapter builds argv** | planner returns `ContainerSpec`/`NetworkSpec`, adapter maps to argv | PASS — keeps core import-pure |
| **Env plan single source of truth (no `DB_NAME`)** | Postgres `{POSTGRES_PASSWORD,POSTGRES_USER,POSTGRES_DB}`, Odoo `{DB_HOST,DB_PORT,DB_USER,DB_PASSWORD,POSTGRES_DB}` — exact entrypoint match; no `DB_NAME` | PASS — test_plan_backend_env_matches_entrypoint |
| **Named PG data + Odoo-filestore volumes** | Both persist across stop→run; created-only rollback never removes pre-existing volumes | PASS — test_reattach_then_fail_preserves_existing_volume |
| **Running-state-first readiness (exited ≠ unknown)** | `parse_status` checks `.State.Running` before health | PASS — test_parse_status_running_state_first |
| **Postgres TCP readiness gate** | `docker exec <db> pg_isready -h 127.0.0.1 -U <user> -d <db>` (bounded retries) | PASS — test_pg_readiness_gate_tcp_scoped |
| **Odoo health-wait default floor ≥180s** | `DEFAULT_HEALTH_WAIT_TIMEOUT_SECONDS = 180.0` (start-period + interval + cold-boot margin) | PASS — test_odoo_health_wait_default_floor |
| **Ephemeral host ports (-p 0:8069/-p 0:8072)** | Supersedes spec's `PortConflict` requirement (collisions structurally unreachable) | PASS — host port reported by status() |
| **Docker adapter via subprocess (not HTTP SDK)** | argv-list, no shell=True, matches existing git/workspace adapters | PASS — Strict TDD compatible, zero real docker/network |
| **5th import-linter contract** | Forbidden `odoo_forge → odoo_forge_docker` | PASS — 5 kept, 0 broken |
| **Status no-raise / stop/logs/exec InstanceNotFoundError** | Divergent paths: status() never raises; others raise | PASS — test_scan_error_from_corrupted_checkout_exits_clean_one_error (parametrized 5 commands) |

---

## Non-Blocking Tracked Debt (Deferred, Not Silent)

| Debt | Issue | Scope | Tracked |
|------|-------|-------|---------|
| **DEBT-1** | `_wait_pg_ready`/`_wait_odoo_healthy` bound by attempt-count, not monotonic wall-clock deadline; under slow daemon real wait can exceed configured timeout (bounded, no leak — SLA imprecision only) | Hardening pass / future slice | PR-2a-ii tasks section |
| **DEBT-2** | `stop`/`logs`/`exec`/`status` derive identity via full workspace scan, blocking pure-identity ops when workspace is corrupted; should derive from `manifest.name`+`instance` without scanning | Couples to `plan_backend(state)` consumption or hardening pass | PR-3b tasks section |

---

## Out of Scope (Explicitly Deferred)

- **4a registry resolution** (`PublishedLayer`/`registry://` resolution, `locking.py:27-29`) — **DEFERRED TO FUTURE SLICE** — evidence in explore.md, confirmed by code comment in locking.py
- **backup/restore** — design §5 buckets to Phase 4
- **Seeding/anonymization** — extension point only, no implementation
- **doctor command** — typed `DockerUnavailableError` covers dependency check this slice

---

## Verification & Compliance

### All Spec Requirements Met

✅ 52-row conformance matrix in verify-report shows every requirement + scenario implemented and test-covered:
- BackendProvider Protocol (3 scenarios)
- import-linter (5 contracts)
- Adapter structural + signature conformance (2 tests)
- Pure planner over manifest+state (16 tests)
- DB env matches entrypoint (no `DB_NAME`, single-source creds)
- Five mount roots, DB_HOST → PG alias, named volumes, determinism
- run() provisioning + readiness gates
- status derives from Docker only, no registry
- Manually-removed container handling
- CLI resilient boundary + typed errors
- Daemon-unavailable (missing binary + daemon-down)
- Partial run() failure (created-only rollback)
- Reattach-then-fail data-loss guard
- stop()/logs()/exec() unknown-instance handling
- exec() exit-code passthrough

### Purity Enforced

- Core imports zero `docker`/`subprocess`/`typer`/`httpx`/`requests` symbols
- Adapter imported ONLY in composition root (`main.py:42`)
- 5th import-linter contract verified: 5 kept, 0 broken

### Non-Goals Respected

- Zero `backup`/`restore`, `destroy`, `doctor`, `registry://` present in code (grep confirmed)

### Tasks Completeness

- All 6 PR task batches: ✅ complete
- Every numbered task box: ✅ checked
- Size exception (PR-2a-ii): documented with root cause + orchestrator visibility
- Debts (DEBT-1, DEBT-2): recorded in tasks section, not silently dropped

---

## Slice 4 Architecture: 4a/4b Split

### What This Slice Delivered (4b)

**Local Docker Backend**: Docker-backed instance lifecycle (run/status/stop/logs/exec), own-Postgres provisioning, pure planner, label-based state introspection.

- ✅ 6 chained PRs, all gates green, fully verified
- ✅ Baseline spec: `openspec/specs/local-backend/spec.md`
- ✅ CLI commands: `forge run`, `forge status`, `forge stop`, `forge logs`, `forge exec`
- ✅ Pure core: `BackendProvider` port + error family + `plan_backend` + `parse_status`
- ✅ Adapter: `odoo_forge_docker` (subprocess-based docker CLI)
- ✅ Import-linter: 5th contract in place

### What Remains Deferred (4a)

**Registry Resolution**: Resolve `PublishedLayer.source`/`version` to lockfile entries via HTTP registry API call.

- 🔮 Separate infrastructure concern (network I/O boundary different from Docker)
- 🔮 Plugs into `build_lock`/`SourceProvider`, not backend chain
- 🔮 Covered by comment in `locking.py:27-29` ("until registry resolution lands")
- 🔮 Deferred to a future slice (alongside `backup`/`restore` → Phase 4, `doctor` → hardening, `destroy` → hardening)

---

## Cross-Session Pointers (Engram)

| Artifact | Type | ID | Purpose |
|----------|------|----|----|
| `sdd/phase-2-slice-4-local-docker-backend/proposal` | Proposal | (ref) | Change scope: port + planner + adapter + 5 CLI commands; 4a/4b split; Postgres provisioning closure |
| `sdd/phase-2-slice-4-local-docker-backend/design` | Design | (ref) | Judgment-day decisions: pure planner + dumb adapter, created-only rollback, PG TCP gate, Odoo health wait ≥180s, parse_status two-stage, named volumes, stop preserves data, status no-raise/others raise, env single-source, docker CLI subprocess, injectable clock seams |
| `sdd/phase-2-slice-4-local-docker-backend/tasks` | Tasks | (ref) | 6 PR batches, 48 numbered tasks, all ✅; size exception (PR-2a-ii 537 lines, root cause documented); DEBT-1/2 tracked; orchestrator boundary instructions recorded |
| `sdd/phase-2-slice-4-local-docker-backend/verify-report` | Verify | (ref) | Gate evidence (242 passed, 5 kept), 52-row conformance matrix, purity proof, non-goals check, CRITICAL/WARNING/SUGGESTION items |

---

## File Inventory

### New Baseline Spec
- `openspec/specs/local-backend/spec.md` — 237 lines, 5 capabilities, 17 scenarios, non-goals documented

### Archived Artifacts
All artifacts moved from `openspec/changes/phase-2-slice-4-local-docker-backend/` to `openspec/changes/archive/2026-07-08-phase-2-slice-4-local-docker-backend/`:
- `proposal.md`
- `design.md`
- `specs/local-backend/spec.md`
- `tasks.md`
- `verify-report.md`
- `explore.md`
- `archive-report.md` (this file, for traceability)

### Code (Merged to main)
- `src/odoo_forge/ports/backend_provider.py` (new)
- `src/odoo_forge/backend/__init__.py` (new)
- `src/odoo_forge/backend/plan.py` (new)
- `src/odoo_forge/backend/status.py` (new)
- `src/odoo_forge/backend/errors.py` (new)
- `src/odoo_forge_docker/__init__.py` (new)
- `src/odoo_forge_docker/provider.py` (new)
- `src/odoo_forge_cli/main.py` (modified — 5 commands + composition root)
- `pyproject.toml` (modified — wheel packages + root packages + 5th import-linter contract + integration marker)
- Test files: `tests/backend/test_plan.py`, `test_status.py`, `tests/adapters/test_docker_provider.py`, `test_docker_provider_integration.py`, `tests/cli/test_backend.py`

---

## Roadmap Update (See Next Step)

Roadmap (`docs/specs/2026-07-06-phase-2-slices-roadmap.md`) updated to:
1. Mark Slice 4 **DONE (archived 2026-07-08)** with 4a/4b split explicit
2. Record what shipped in Slice 4b (this slice) vs what 4a (registry resolution) defers
3. Add DEBT-1/DEBT-2 pointers to non-blocking debt section
4. Preserve 4a as a future slice with its own scope boundary

---

## Summary

✅ **Slice 4b is complete, verified, and archived.**

The slice successfully implements the first `BackendProvider` to turn Slice-3 workspace projections into live Odoo instances on Docker. Pure core planner and dumb subprocess adapter maintain the proven ports/adapters spine. All spec requirements met, gates green, purity enforced, debts tracked. The 4a/4b split is explicit and documented — registry resolution deferred as a separate future slice.

Ready for the next slice.
