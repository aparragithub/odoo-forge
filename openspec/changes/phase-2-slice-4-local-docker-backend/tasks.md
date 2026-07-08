# Tasks: Phase 2 Slice 4b — Local Docker Backend

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR-1a ~280-350, PR-1b ~200-260, PR-2a ~300-380, PR-2b ~250-320, PR-3a ~220-300, PR-3b ~180-250 |
| 400-line budget risk | Medium overall bundle; Low-Medium per PR once split |
| Chained PRs recommended | Yes (6) |
| Suggested split | PR 1a → PR 1b → PR 2a → PR 2b → PR 3a → PR 3b |
| Delivery strategy | feature-branch-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

The full bundle (port + pure planner/parser + docker adapter + own-Postgres +
5 CLI commands + 5th import-linter contract) exceeds 400 lines as a single PR
and the adapter alone (run/rollback + status/stop/logs/exec) is large enough
to warrant its own split, so the chain grows to 6 PRs (one more than Slice
3's precedent, reflecting the extra readiness/rollback surface).

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1a | `BackendProvider` port, `BackendError` family, `backend/plan.py` (`ContainerRole`, specs, `plan_backend`, `sanitize_name`) | PR 1a | base = feature/tracker branch; zero I/O, fakeable |
| 1b | `backend/status.py` (`InstanceRef`/`InstanceStatus`/`ExecResult`, `instance_ref`, pure `parse_status`) | PR 1b | base = PR 1a branch; pure parser, no docker |
| 2a | `odoo_forge_docker` adapter — `run` orchestration, PG/Odoo readiness gates, injectable clock, created-only rollback | PR 2a | base = PR 1b branch; introduces the sibling package |
| 2b | `odoo_forge_docker` adapter — `status`/`stop`/`logs`/`exec` + contract conformance tests | PR 2b | base = PR 2a branch; completes the adapter's 5 port methods |
| 3a | `forge run`/`forge status` CLI + `_make_backend_provider()` + 5th import-linter contract + roadmap note | PR 3a | base = PR 2b branch; consumes PR 1a/1b/2a/2b |
| 3b | `forge stop`/`forge logs`/`forge exec` CLI + integration marker wiring | PR 3b | base = PR 3a branch; smallest unit |

Recommended review lenses: review-resilience + review-reliability (subprocess
boundary, rollback/idempotency, partial-failure modes) for PR-2a, PR-2b, PR-3a.

## PR-1a: Port, Errors, Pure Planner

### Phase 1: Port & Errors
- [x] 1.1 Create `ports/backend_provider.py` — `@runtime_checkable BackendProvider` Protocol (`run`/`status`/`stop`/`logs`/`exec`, final signatures)
- [x] 1.2 RED: `test_errors.py::test_backend_error_family` — `DockerUnavailableError`/`ImageNotFoundError`/`PostgresReadinessError`/`ContainerRunError`/`InstanceNotFoundError`/`InstanceExistsError` subclass `BackendError`
- [x] 1.3 GREEN: `backend/errors.py` — `BackendError` family

### Phase 2: Planner types + sanitize_name (`backend/plan.py`)
- [x] 2.1 Create `backend/__init__.py` package marker
- [x] 2.2 Define `ContainerRole` (`"odoo" | "postgres"`) explicitly in `backend/plan.py`
- [x] 2.3 RED: `test_plan.py::test_sanitize_name_*` — already-valid unchanged (no suffix), empty-after-sanitize, invalid-first-char, two raw names sharing a sanitized stem -> distinct
- [x] 2.4 GREEN: implement `sanitize_name(raw) -> str` (always-on lossy-hash-suffix rule)
- [x] 2.5 RED: `test_plan.py::test_plan_backend_env_matches_entrypoint` — Postgres `{POSTGRES_PASSWORD,POSTGRES_USER,POSTGRES_DB}`, Odoo `{DB_HOST,DB_PORT,DB_USER,DB_PASSWORD,POSTGRES_DB}` match `factory/entrypoint.sh:143-159`; no `DB_NAME`; shared user/password/db equal across containers
- [x] 2.6 RED: `test_plan.py::test_plan_backend_mounts_five_roots`
- [x] 2.7 RED: `test_plan.py::test_plan_backend_db_host_resolves_to_postgres_alias`
- [x] 2.8 RED: `test_plan.py::test_plan_backend_volumes_named_pg_and_filestore`
- [x] 2.9 RED: `test_plan.py::test_plan_backend_volume_list_consistency` — top-level `plan.volumes` (create set) equals exactly the volumes referenced by `plan.postgres.volumes`/`plan.odoo.volumes` (mount set)
- [x] 2.10 RED: `test_plan.py::test_plan_backend_deterministic`
- [x] 2.11 GREEN: implement `NetworkSpec`/`VolumeSpec`/`ContainerSpec`/`BackendPlan` + `plan_backend(manifest, state, instance="default")` satisfying 2.5-2.10

### Phase 2b: review-reliability follow-up (pre-merge gap closure)
- [x] 2.12 `tests/ports/test_backend_provider.py` — conforming fake satisfies `isinstance(fake, BackendProvider)`; non-conforming class (missing `exec`) does not, proving the port contract is satisfiable without PR-1b's status types
- [x] 2.13 `test_plan.py::test_image_fields_are_exact` — explicit `plan.odoo.image`/`plan.postgres.image` regression assertions
- [x] 2.14 `test_plan.py::test_distinct_all_invalid_names_both_empty_after_sanitize_are_distinct` — two all-invalid raw names (`"!!!"`/`"???"`) both empty-after-sanitize still yield distinct outputs
- [x] 2.15 `test_plan.py::test_mounts_identical_with_an_empty_materialized_state` — empty `MaterializedState` yields the same fixed mount table as a populated one

**PR-1a Gate**: `uv run pytest` + `uv run lint-imports` (no regression, 4 contracts).

## PR-1b: Pure Status Parser (`backend/status.py`)

### Phase 3: InstanceRef/InstanceStatus/ExecResult + parse_status
- [x] 3.1 RED: `test_status.py::test_parse_status_running_state_first` (both roles) — `Running=false` maps to not-running/exited regardless of role or stale health, never `unknown`
- [x] 3.2 RED: `test_status.py::test_parse_status_odoo_health_mapping` — `starting`/`unhealthy`/`healthy`/null-on-running -> `unknown`
- [x] 3.3 RED: `test_status.py::test_parse_status_postgres_null_health_running_not_unready` — running Postgres with null health is "no-healthcheck" running, not not-ready
- [x] 3.4 RED: `test_status.py::test_parse_status_empty_absent_inspect_not_running_no_raise`
- [x] 3.5 GREEN: implement `InstanceRef`/`InstanceStatus`/`ExecResult` (pydantic) + `instance_ref()` + `parse_status(json)` — two-stage (running-first, then per-role health)

**PR-1b Gate**: `uv run pytest` + `uv run lint-imports`. ✅ 176 passed, 0 failed; 4 kept, 0 broken.

## PR-2a: Docker Adapter — run() Orchestration + Rollback

> **Split note**: PR-2a's full implementation (all of Phase 4-7) was completed
> and green as one cohesive unit (~610 changed lines), but that exceeded the
> 400-line review budget. Per orchestrator decision, delivery was chunked into
> two landable PRs along the natural task-phase seam, reusing the exact
> already-tested code (no re-derivation):
> - **PR-2a-i** (argv + errors): package scaffold, pure argv builders,
>   `_docker_env`, `_health_status`, the subprocess boundary (`_run_raw`/`_exec`),
>   error classification, and existence checks (`_exists`/`_network_exists`/
>   `_volume_exists`/`_container_exists`). No `run()`, no rollback, no
>   readiness gates yet — this class does not satisfy the `BackendProvider`
>   Protocol on its own.
> - **PR-2a-ii** (run + rollback): `run()` orchestration, readiness gates
>   (`_wait_pg_ready`/`_wait_odoo_healthy`, injectable clock), created-only
>   rollback (`_ensure_network`/`_ensure_volume`/`_run_container`/`_rollback`),
>   and the pre-run existence gate (`InstanceExistsError`).
> - **review-reliability fix (still PR-2a-i)**: the initial PR-2a-i cut only
>   tested `_run_container_argv` via the postgres spec (empty mounts/ports),
>   leaving the dynamic host-port binding (`host_port is None -> "0"`) and the
>   `:ro` read-only mount suffix untested — both are live in the shipped Odoo
>   container spec (`ports={"8069": None, "8072": None}`, mixed `read_only`
>   mounts). Added `test_run_container_argv_ephemeral_ports_and_readonly_mount_suffix`
>   pinning both. The `_health_status` no-healthcheck (`Health` absent) and
>   empty-inspect-list (`[]`) edge cases were deliberately deferred to Phase 5
>   (tasks 5.5/5.6) since they belong with `_wait_odoo_healthy`'s consumer
>   loop, not the isolated pure-helper tests.

### Phase 4: Package scaffold + argv plumbing
- [x] 4.1 Create `odoo_forge_docker/__init__.py` package marker (PR-2a-i)
- [x] 4.1a (PR-2a-i) RED+GREEN: pure argv builders (`_network_create_argv`/`_volume_create_argv`/`_run_container_argv`) + `_docker_env` (`LANG=C`/`LC_ALL=C`) — unit-tested directly in `test_docker_provider.py` without a full `run()`
- [x] 4.2 RED: `test_docker_provider.py::test_run_argv_network_volume_container_order` — exact `docker` argv sequence (network create, volume create x2, run pg, exec pg_isready, run odoo) through the full `run()` orchestration (PR-2a-ii)
- [x] 4.3 GREEN: implement `DockerBackendProvider.run()` composing the PR-2a-i argv builders via `subprocess.run` (monkeypatched like `test_git_provider.py`) (PR-2a-ii)

### Phase 5: Readiness gates + injectable clock (PR-2a-ii)
- [x] 5.1 RED: `test_docker_provider.py::test_pg_readiness_gate_tcp_scoped` — `docker exec <db> pg_isready -h 127.0.0.1 -U <user> -d <db>`; bounded retries via injectable clock; timeout raises `PostgresReadinessError`
- [x] 5.2 GREEN: implement PG readiness gate with constructor-injected sleep/clock seam (default `time.sleep`)
- [x] 5.3 RED: `test_docker_provider.py::test_odoo_health_wait_default_floor` — default timeout is configurable and floors at >=180s
- [x] 5.4 GREEN: implement Odoo health-wait polling `docker inspect .State.Health.Status == healthy`, configurable timeout (default floor >=180s), injectable clock; timeout raises `ContainerRunError`
- [x] 5.5 `test_docker_provider.py::test_health_status_no_healthcheck_configured` — `_health_status` returns `None` when `.State.Health` is absent (no `HEALTHCHECK` on the image), exercised via `_wait_odoo_healthy`'s polling loop (deferred from PR-2a-i per review-reliability finding: belongs with the health-wait consumer, not the isolated pure-helper tests)
- [x] 5.6 `test_docker_provider.py::test_health_status_empty_inspect_list` — `_health_status` returns `None` when `docker inspect` returns `[]` (container removed mid-poll), exercised via `_wait_odoo_healthy`'s polling loop (deferred from PR-2a-i, same reason as 5.5)

### Phase 6: Created-only rollback (PR-2a-ii)
- [x] 6.1 RED: `test_docker_provider.py::test_partial_failure_rollback_removes_only_created_resources` — reverse-order `docker rm -f -v` (containers), `docker volume rm` (created volumes only), `docker network rm`
- [x] 6.2 RED: `test_docker_provider.py::test_reattach_then_fail_preserves_existing_volume` — pre-existing named PG/filestore volume is never pushed onto the rollback stack and is NOT removed on a subsequent failure
- [x] 6.3 GREEN: implement existence-check-before-create + created-resource rollback stack, teardown scoped to `com.odoo-forge.managed=true`

### Phase 7: run() error classification
- [x] 7.1 RED+GREEN: `test_docker_provider.py::test_run_raw_raises_docker_unavailable_on_missing_binary` — `FileNotFoundError` -> `DockerUnavailableError` (PR-2a-i, via `_run_raw`)
- [x] 7.2 RED+GREEN: `test_docker_provider.py::test_exec_raises_docker_unavailable_on_daemon_down_stderr_marker` — non-zero exit + `Cannot connect to the Docker daemon` -> `DockerUnavailableError` (PR-2a-i, via `_exec`); existence-check daemon-down path also covered by `test_exists_raises_docker_unavailable_on_daemon_down_marker`
- [x] 7.3 RED+GREEN: `test_docker_provider.py::test_exec_raises_image_not_found_on_stderr_marker` -> `ImageNotFoundError` (PR-2a-i, via `_exec`)
- [x] 7.4 RED: `test_docker_provider.py::test_run_refuses_existing_instance` — `InstanceExistsError` when a named container/network already exists, running OR stopped (PR-2a-ii, requires `run()`)
- [x] 7.5 GREEN: implement pre-run existence check wiring `InstanceExistsError` into `run()` (PR-2a-ii; the underlying `_container_exists`/`_network_exists`/`_volume_exists` checks and generic error classification are already implemented and tested in PR-2a-i)

**PR-2a-i Gate**: `uv run pytest` + `uv run lint-imports`. ✅ 191 passed, 0 failed; 4 kept, 0 broken. Changed lines: 390 (1 + 155 + 230 + 4, under the 400-line budget) — includes the review-reliability coverage fix for `_run_container_argv` ephemeral ports + `:ro` mounts.

**PR-2a-ii Gate**: `uv run pytest` + `uv run lint-imports`. ✅ 204 passed, 0 failed (191 PR-2a-i baseline + 13 net new PR-2a-ii tests); 4 kept, 0 broken (5th contract still deferred to PR-3a). Changed lines (git diff, modified files): `provider.py` 133+15=148, `test_docker_provider.py` 300+3=303 → **451 changed lines, OVER the 400-line budget by 51 lines (~13%)**. Root cause: this batch ports 14 already-judgment-day-hardened tests verbatim from the snapshot (full `run()` ordering, PG readiness success/timeout, Odoo health default-floor/timeout, created-only rollback, the CRITICAL reattach-then-fail data-loss guard, `InstanceExistsError` precheck, 3 error-classification-via-`run()` variants, plus the 2 deferred `_health_status` edge cases) — none of which can be dropped without losing coverage the design/judgment-day process already mandated. Not re-split further per orchestrator's explicit PR-2a-i/PR-2a-ii boundary instruction; flagged here for orchestrator visibility instead.

### Phase 7b: review-reliability + review-resilience follow-up (pre-merge blocker fix, still PR-2a-ii)
- [x] 7.6 `_run_raw` now catches `subprocess.TimeoutExpired` (in addition to `FileNotFoundError`) and raises `DockerUnavailableError` — mirrors `git_provider.py`/`workspace/provider.py`'s existing timeout-to-typed-error pattern; a docker call that never returns means the daemon is unresponsive, so `DockerUnavailableError` is the correct classification
- [x] 7.7 `_rollback` now wraps EACH teardown step in its own `try/except Exception: continue` so one stuck/failing/timed-out step never aborts the remaining teardowns and never masks the original `run()` failure; docstring corrected to state the actual best-effort-per-step guarantee
- [x] 7.8 Tests added: `test_run_raw_raises_docker_unavailable_on_timeout`, `test_exec_raises_docker_unavailable_on_timeout`, `test_rollback_continues_after_one_teardown_step_raises` (odoo `docker rm` times out; asserts pg container/both volumes/network are still torn down and the original `ContainerRunError` from `run()` is what propagates, not the cleanup-time exception)
- [x] 7.9 Added a one-line comment at the `InstanceExistsError` precheck in `run()` explaining `docker inspect` exits 0 for a container in ANY state (running or stopped), so one `_container_exists` check already covers both — no separate running-vs-stopped branch needed

**PR-2a-ii Gate (post-fix, FINAL)**: `uv run pytest` + `uv run lint-imports`. ✅ 207 passed, 0 failed (204 + 3 new); 4 kept, 0 broken. Final changed lines for the whole PR-2a-ii scope (git diff vs. PR-2a-i merge point): `provider.py` 159+17=176, `test_docker_provider.py` 358+3=361 → **537 changed lines total, OVER the 400-line budget by 137 lines (~34%)** once the blocker fix + its 3 tests are included. Same root cause as above (verbatim-ported, judgment-day-mandated coverage) plus 3 additional required tests for the timeout-handling/rollback-resilience blocker. Flagged for orchestrator visibility; not re-split per explicit scope instruction to fix this blocker within PR-2a-ii.

### Debt (tracked, not implemented — deferred past PR-2a-ii)
- [ ] DEBT-1 Refine `_wait_pg_ready`/`_wait_odoo_healthy` to a monotonic-deadline budget instead of attempt-count: today `attempts = timeout / poll_interval` bounds the number of polls, but each poll's own `docker` subprocess call can itself take up to `docker_timeout`, so under a slow/degraded daemon the real wall-clock wait can exceed the configured `pg_readiness_timeout`/`health_wait_timeout` (bounded — no leak — just SLA imprecision). Track for PR-2b or a follow-up hardening pass.

## PR-2b: Docker Adapter — status/stop/logs/exec + Contract Conformance

### Phase 8: status/stop
- [x] 8.1 RED: `test_docker_provider.py::test_status_derives_from_inspect_labels_no_registry`
- [x] 8.2 RED: `test_docker_provider.py::test_status_absent_container_not_running_no_raise`
- [x] 8.3 GREEN: implement `status()` — `docker inspect` + label filter, delegates to `parse_status`
- [x] 8.4 RED: `test_docker_provider.py::test_stop_argv_preserves_named_volumes` — stop + `rm -f -v` + network rm, named PG/filestore volumes untouched
- [x] 8.5 RED: `test_docker_provider.py::test_stop_unknown_instance_raises_instance_not_found`
- [x] 8.6 GREEN: implement `stop()` — `docker stop` + `rm -f -v` + `network rm`, `InstanceNotFoundError` when absent

### Phase 9: logs/exec
- [x] 9.1 RED: `test_docker_provider.py::test_logs_returns_str_per_role`
- [x] 9.2 RED: `test_docker_provider.py::test_logs_absent_instance_raises_instance_not_found`
- [x] 9.3 GREEN: implement `logs(ref, role) -> str`
- [x] 9.4 RED: `test_docker_provider.py::test_exec_returns_exit_code_stdout_stderr`
- [x] 9.5 RED: `test_docker_provider.py::test_exec_absent_instance_raises_instance_not_found`
- [x] 9.6 GREEN: implement `exec(ref, argv) -> ExecResult`

### Phase 10: Contract conformance
- [x] 10.1 RED: `test_docker_provider.py::test_isinstance_backend_provider_conformance`
- [x] 10.2 RED: `test_docker_provider.py::test_signature_conformance_per_method` — `inspect.signature` comparison per method vs the port (isinstance alone verifies names only)
- [x] 10.3 GREEN: reconcile signatures until both pass

**PR-2b Gate**: `uv run pytest` + `uv run lint-imports`. ✅ 219 passed, 0 failed (207 PR-2a-ii baseline + 12 net new PR-2b tests: 3 status, 3 stop [incl. partial-instance case], 2 logs, 2 exec, 2 conformance); 4 kept, 0 broken (5th contract still deferred to PR-3a). Changed lines (git diff --numstat vs PR-2a-ii): `provider.py` 74+3=77, `test_docker_provider.py` 249+1=250 → **327 changed lines, under the 400-line budget**.

**Post-review-reliability follow-up (still PR-2b, pre-merge)**: two should-fix items closed:
1. `test_signature_conformance_per_method` strengthened from a names-only `list(inspect.signature(...).parameters)` comparison to also compare every parameter's AND the return's type annotation via `typing.get_type_hints` (with an explicit `localns` supplying the port's `TYPE_CHECKING`-only types, since the port uses `from __future__ import annotations`) — now catches drift like `logs(...) -> str` becoming `-> bytes` or `role: ContainerRole` becoming `role: str`.
2. Added `test_stop_partial_instance_stops_only_existing_container` — covers the previously-untested `if not exists: continue` branch in `stop()` (postgres exists, odoo does not): asserts only the existing container is stopped/removed, the network is still removed, and no `docker volume rm` occurs.

## PR-3a: forge run/status CLI + Composition Root + 5th Contract

### Phase 11
- [x] 11.1 RED: `tests/cli/test_backend.py::test_run_succeeds_prints_instance_ref` (monkeypatched `_make_backend_provider`)
- [x] 11.2 GREEN: add `_make_backend_provider()` + `forge run [--manifest][--instance]` calling `plan_backend` + `provider.run` (input assembly mirrors `validate`'s manifest-load + workspace-scan + `materialize_state` path; `--lock` was dropped from the flag set since `plan_backend` never consumes a lockfile — kept identical to `validate`'s actual inputs rather than adding an unused option)
- [x] 11.3 RED: `test_backend.py::test_run_docker_unavailable_single_line_exit1_no_traceback`
- [x] 11.4 GREEN: catch `BackendError` family, exit 1 with a single-cause message
- [x] 11.5 RED: `test_backend.py::test_status_reports_not_running_without_raising_for_absent_instance`
- [x] 11.6 GREEN: `forge status [--manifest][--instance]` calling `plan_backend` -> `instance_ref` -> `provider.status()`, never raises for an absent instance
- [x] 11.7 Added the 5th import-linter contract (forbidden `odoo_forge -> odoo_forge_docker`); `odoo_forge_docker` was already present in `pyproject.toml` wheel packages + `root_packages` from PR-2a/2b. Integration pytest marker registration explicitly deferred to PR-3b per scope.
- [x] 11.8 Verify `uv run lint-imports` — 5 kept, 0 broken
- [x] 11.9 Update `docs/specs/2026-07-06-phase-2-slices-roadmap.md` — record the 4a/4b split

**PR-3a Gate (initial pass)**: `uv run pytest` + `uv run lint-imports`. ✅ 222 passed, 0 failed (219 PR-2b baseline + 3 net new CLI tests: run success, run `DockerUnavailableError`, status absent-instance); 5 kept, 0 broken (new "Core never imports the docker adapter" contract). Changed lines (git diff --numstat + new file line count): `main.py` 104 additions, `pyproject.toml` 6 additions, `tests/cli/test_backend.py` 150 (new file) → **260 changed lines, under the 400-line budget**.

**Post-review-reliability follow-up (still PR-3a, pre-merge)**: one BLOCKER + one CRITICAL closed:
1. **BLOCKER — incomplete error boundary**: `run`/`status` only caught `BackendError`, but `workspace_provider.scan()`/`materialize_state()` (the SAME call `project`/`validate` make) raise `ScanError` (`WorkspaceError` -> `ManifestError`), NOT a `BackendError` — a corrupted checkout crashed with a raw traceback instead of a clean exit. Fixed by widening both commands' `except` clause to `except (ManifestError, BackendError) as exc`, mirroring `project`'s boundary exactly. Added `test_scan_error_from_corrupted_checkout_exits_clean_one_error` (parametrized over `run`/`status`).
2. **CRITICAL — unsanitized `--instance`**: `plan_backend` sanitized `manifest.name` via `sanitize_name` but interpolated the now-user-facing `instance` argument RAW into every docker resource name/label — a messy `--instance` value (spaces/uppercase/`/`) could produce an invalid docker name or a divergent identity between independent `plan_backend` calls. Fixed in `src/odoo_forge/backend/plan.py`: `instance = sanitize_name(instance)` added right after `project = sanitize_name(manifest.name)`, so `instance` is normalized through the SAME single source of truth before use. Added `test_instance_is_sanitized_consistently_and_deterministically` to `tests/backend/test_plan.py` (core PR-1a code, correctly touched here since this PR is what exposed the bug by making `--instance` user-facing).
3. **Should-fix edge cases added**: `test_run_instance_exists_exits_clean_one_error` (pins the `InstanceExistsError` path the `run` docstring claims is handled), `test_missing_manifest_exits_clean_one_error` + `test_malformed_manifest_exits_clean_one_error` (both parametrized over `run`/`status`).

**PR-3a Gate (FINAL, post-fix)**: `uv run pytest -q` → **230 passed**, 0 failed. `uv run lint-imports` → **5 kept, 0 broken** (unchanged). Changed lines (git diff --numstat + new-file line count, full PR-3a scope): `main.py` 108, `pyproject.toml` 6, `src/odoo_forge/backend/plan.py` 8, `tests/backend/test_plan.py` 21, `tests/cli/test_backend.py` 227 (new file) → **370 changed lines, under the 400-line budget**.

## PR-3b: forge stop/logs/exec CLI + Integration Marker

### Phase 12
- [ ] 12.1 RED: `test_backend.py::test_stop_unknown_instance_exits_nonzero_single_cause`
- [ ] 12.2 GREEN: `forge stop [--instance]` calling `provider.stop()`, catch `InstanceNotFoundError`
- [ ] 12.3 RED: `test_backend.py::test_logs_prints_role_selected_log_text`
- [ ] 12.4 GREEN: `forge logs [--instance][--role]` calling `provider.logs()`
- [ ] 12.5 RED: `test_backend.py::test_exec_prints_stdout_and_propagates_exit_code`
- [ ] 12.6 GREEN: `forge exec [--instance] -- ARGV` calling `provider.exec()`, surfaces `exit_code`
- [ ] 12.7 Mark real-daemon-only behaviors (PG socket-vs-TCP race, ephemeral-port assignment, health timing) `@pytest.mark.integration`; deselect from the default Strict-TDD unit run via `pyproject.toml` pytest config

**PR-3b Gate**: `uv run pytest` (unit-only, integration deselected) + `uv run lint-imports` (5 kept, 0 broken) + manual `forge --help` showing `run`/`status`/`stop`/`logs`/`exec`.

## Scope Guardrails
- No `backup`/`restore` — deferred to Phase 4 (design §5).
- No `doctor` command — `DockerUnavailableError` covers the dependency check this slice.
- No `destroy` op — `stop` preserves named volumes by design; reclaim is a future slice.
- No 4a registry resolution (`PublishedLayer`/`registry://`) — tracked separately.
