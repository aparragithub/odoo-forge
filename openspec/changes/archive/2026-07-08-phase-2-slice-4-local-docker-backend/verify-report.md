# Verification Report: phase-2-slice-4-local-docker-backend

**Change**: phase-2-slice-4-local-docker-backend (Local Docker Backend, Phase 2 Slice 4b)
**Mode**: hybrid (Engram + openspec file)
**Artifacts read**: spec.md, design.md, tasks.md, Engram apply-progress (#2343)
**Scope**: full slice, all 6 chained PRs merged (1a/1b/2a-i/2a-ii/2b/3a/3b)

## VERDICT: PASS

All spec requirements are implemented by real code AND covered by a passing test.
Every judgment-day-hardened design decision is concretely present. Both gates are
green. No non-goal leaked in. Two tracked debts (DEBT-1, DEBT-2) and one
size:exception (PR-2a-ii) are explicitly recorded, not silently dropped —
non-blocking for archive.

## Gate Evidence (run in this verification, not trusted from claims)

| Gate | Command | Result |
|---|---|---|
| Tests | `uv run pytest -q` | **242 passed, 1 deselected** in 1.09s |
| Imports | `uv run lint-imports` | **5 kept, 0 broken** (41 files, 92 deps analyzed) |

The 1 deselected test is the `@pytest.mark.integration` real-daemon skeleton
(`tests/adapters/test_docker_provider_integration.py`), correctly deselected by
`addopts = "-m 'not integration'"` — suite is hermetic, no real docker.

## Spec Conformance Matrix

| Requirement / Scenario | Implementing symbol | Covering test | Status |
|---|---|---|---|
| BackendProvider Protocol (run/status/stop/logs/exec, no backup/restore) | `ports/backend_provider.py` | `tests/ports/test_backend_provider.py` (2) | PASS |
| import-linter enforces purity (5 contracts) | `pyproject.toml` contracts 1-5 | `uv run lint-imports` 5 kept/0 broken | PASS |
| Adapter satisfies port structurally (isinstance) | `DockerBackendProvider` | `test_isinstance_backend_provider_conformance` | PASS |
| Adapter matches signatures not just names | — | `test_signature_conformance_per_method` (type-hint compare) | PASS |
| plan_backend pure over manifest+state | `backend/plan.py::plan_backend` | `tests/backend/test_plan.py` (16) | PASS |
| DB env matches entrypoint (no DB_NAME, single-source creds) | `plan.py` postgres/odoo env | `test_plan_backend_env_matches_entrypoint` | PASS |
| Five mount roots | `plan.py` MOUNT_ROOTS loop | `test_plan_backend_mounts_five_roots` | PASS |
| DB_HOST -> PG network alias (not localhost) | `env["DB_HOST"]=postgres_name` | `test_plan_backend_db_host_resolves_to_postgres_alias` | PASS |
| Named PG data + Odoo filestore volumes | `plan.volumes` (pgdata+filestore) | `test_plan_backend_volumes_named_pg_and_filestore` | PASS |
| create-set == mount-set invariant | `plan.volumes` vs container volumes | `test_plan_backend_volume_list_consistency` | PASS |
| Plan deterministic | pure `plan_backend` | `test_plan_backend_deterministic` | PASS |
| run() provisions own Postgres, readiness-gated | `provider.run` + `_wait_pg_ready`/`_wait_odoo_healthy` | `test_run_argv_...`, `test_pg_readiness_gate_tcp_scoped`, `test_odoo_health_wait_default_floor` | PASS |
| status derives from Docker only, no registry | `provider.status` + `parse_status` | `test_status_derives_from_inspect_labels_no_registry` | PASS |
| Manually-removed container -> not-running no-raise | `parse_status` absent path | `test_status_absent_container_not_running_no_raise`, `test_empty_list_maps_to_not_running...` | PASS |
| CLI resilient boundary, typed taxonomy, Exit(1) | `main.py` run/status/stop/logs/exec | `test_run_docker_unavailable_single_line_exit1_no_traceback` | PASS |
| Daemon-unavailable (both missing-binary + down-daemon) | `_run_raw` FileNotFoundError + `_DAEMON_DOWN_MARKER` | `test_run_raw_raises_docker_unavailable_*` | PASS |
| Partial run() failure: created-only rollback | `provider._rollback` created stack | `test_partial_failure_rollback_removes_only_created_resources` | PASS |
| Reattach-then-fail preserves existing volume (data-loss guard) | existence-check-before-create | `test_reattach_then_fail_preserves_existing_volume` | PASS |
| stop() unknown instance -> InstanceNotFoundError | `provider.stop` | `test_stop_unknown_instance_exits_nonzero_single_cause` | PASS |
| status vs stop/logs/exec absent-instance divergence | status no-raise; others raise | `test_scan_error...` (parametrized 5 cmds) + status test | PASS |
| exec propagates exit_code | `exec_` -> `raise typer.Exit(code=result.exit_code)` | `test_exec_prints_stdout_and_propagates_exit_code` | PASS |

## Design Conformance (judgment-day-hardened decisions)

| Decision | Concrete evidence | Status |
|---|---|---|
| Env plan matches entrypoint (POSTGRES_DB selector, no DB_NAME) | `plan.py:174-201` — odoo env `{DB_HOST,DB_PORT,DB_USER,DB_PASSWORD,POSTGRES_DB}`, pg `{POSTGRES_PASSWORD,POSTGRES_USER,POSTGRES_DB}`, no DB_NAME | PASS |
| Single-source shared credentials | `_DB_USER`/`_DB_PASSWORD`/`db_name` reused across both specs | PASS |
| Named PG + filestore volumes; create==mount | `plan.volumes=[pgdata,filestore]`, mounted on each spec | PASS |
| Created-only rollback | `run` uses `created: list`, `_ensure_*` appends only on create | PASS |
| Reattach-then-fail preserves pre-existing volume (no volume rm) | `_ensure_volume` returns early if `_volume_exists` | PASS |
| Rollback per-step best-effort | `_rollback` per-step `try/except Exception: continue` | PASS |
| TimeoutExpired -> DockerUnavailableError | `_run_raw` catches `subprocess.TimeoutExpired` | PASS |
| parse_status running-state-first (exited != unknown) | `_role_status` checks `.State.Running` before health | PASS |
| absent inspect -> not-running no-raise | `parse_status` None/empty -> `_NOT_RUNNING` | PASS |
| pg_isready TCP gate (-h 127.0.0.1 -U -d) | `_wait_pg_ready` argv | PASS |
| Odoo health wait default floor >=180s | `DEFAULT_HEALTH_WAIT_TIMEOUT_SECONDS = 180.0` | PASS |
| stop preserves named volumes (no volume rm) | `stop` issues `rm -f -v` on containers only, never `volume rm` | PASS |
| status no-raise / stop/logs/exec InstanceNotFoundError | divergent branches in provider | PASS |
| exec propagates ExecResult.exit_code | `_run_raw` no-raise on nonzero; CLI Exit(code) | PASS |
| (ManifestError, BackendError) shared boundary | all 5 CLI commands | PASS |
| 5th import-linter contract (forbidden odoo_forge->odoo_forge_docker) | `pyproject.toml:73-77` | PASS |
| docker adapter imported ONLY in composition root | `main.py:42` sole import; contract proves core-clean | PASS |
| integration deselected by default | `addopts = "-m 'not integration'"` | PASS |

## Purity

`odoo_forge` core imports zero `docker`/`subprocess`/`typer`/`httpx`/`requests`
symbols and never imports the adapter — proven by import-linter (5 kept, 0
broken). The port uses `from __future__ import annotations` + TYPE_CHECKING so it
carries no runtime import of adapter-side types.

## Non-goals Respected

CLI command surface = `validate`, `lock`, `project`, `unlock` (pre-existing 4) +
`run`, `status`, `stop`, `logs`, `exec` (5 new). NO `backup`/`restore`, NO
`destroy`, NO `doctor`, NO `registry://`/`PublishedLayer` resolution present in
core, adapter, or CLI. Confirmed via grep — zero matches.

## Tasks Completeness

Every task box is `[x]` except the two intentionally-unchecked DEBT items.
DEBT-1 and DEBT-2 are recorded in the Slice Close-Out section as deferred (not
dropped). PR-2a-ii size:exception (537 changed lines, ~34% over the 400-line
budget) is documented in the PR-2a-ii Gate section with root cause
(verbatim-ported judgment-day-mandated coverage) and orchestrator visibility.

## Issues

### CRITICAL
None.

### WARNING
None (blocking). Non-blocking observations below.

### SUGGESTION / Tracked Debt (non-blocking)
- **DEBT-1**: `_wait_pg_ready`/`_wait_odoo_healthy` bound polls by attempt-count,
  not a monotonic wall-clock deadline; under a slow daemon the real wait can
  exceed the configured timeout (bounded, no leak — SLA imprecision only).
  Deferred to a future hardening pass.
- **DEBT-2**: `stop`/`logs`/`exec`/`status` derive identity via a full workspace
  scan, so a corrupted/absent workspace blocks pure-identity ops with a clean
  `ScanError -> Exit(1)`. Should derive identity from `manifest.name`+`instance`
  without scanning. Deferred (couples to `plan_backend(state)` consumption).
  Current safe behavior documented by `test_scan_error_from_corrupted_checkout...`.
- **PR-2a-ii size:exception**: recorded, accepted per orchestrator boundary
  instruction; not a correctness issue.

## Summary

The slice fully satisfies its spec and design. All gates green, all scenarios
test-covered, purity enforced, non-goals excluded, debts tracked. Ready for
archive.
