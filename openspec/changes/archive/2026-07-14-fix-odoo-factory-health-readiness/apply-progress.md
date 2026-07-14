# Apply Progress: Fix Odoo Factory Health Readiness

## Child #1 — Readiness Deadline and Recovery

**Mode:** Strict TDD

### Completed Tasks

- [x] 1.1 Characterize the 180-second default and require a 300-second default while retaining the constructor override.
- [x] 1.2 Cover recovery from `unhealthy` and retrying missing, unknown, and `starting` Docker health states.
- [x] 2.1 Set the provider-owned Docker health deadline default to 300 seconds.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/adapters/test_docker_provider.py` | Unit (fake Docker clock) | `uv run pytest tests/adapters/test_docker_provider.py -q` → 70 passed | `test_odoo_health_wait_default_is_300_seconds_and_override_is_retained` first failed: actual `180.0`, expected `300.0` | `uv run pytest tests/adapters/test_docker_provider.py -q` → 76 passed | Default and explicit `3.0` override | None needed; the constant is the minimal implementation |
| 1.2 | `tests/adapters/test_docker_provider.py` | Unit (fake Docker clock) | Same 70-pass baseline | Tests were written before production change; recovery and retry cases passed as approval characterization because existing monotonic polling already satisfies this design behavior | Same 76-pass command | `unhealthy`, missing (`[]`), malformed/unknown, and `starting` each recover to `healthy`; existing deadline tests retain no-probe/no-sleep-after-expiry coverage | None needed; no polling logic change was required |
| 2.1 | `tests/adapters/test_docker_provider.py` | Unit (fake Docker clock) | Same 70-pass baseline | 300-second default assertion failed before the constant change | Same 76-pass command | Explicit constructor override remains `3.0`; existing deadline parametrization proves capped probes/sleeps and monotonic accounting | Simplified the stale comment to the selected two-envelope rationale; tests remained green |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_docker_provider.py -q` — exit 0, **76 passed** in 2.38s. |
| Static check and exact result | `uv run ruff check src/odoo_forge_docker/provider.py tests/adapters/test_docker_provider.py` — exit 0, **All checks passed!** |
| Runtime harness command/scenario and exact result | N/A — Child #1 changes only deterministic provider timeout defaults and fake-clock polling behavior. The real Docker baseline is intentionally reserved for Phase 3/Child #2 evidence and was not run. |
| Rollback boundary | Revert `DEFAULT_HEALTH_WAIT_TIMEOUT_SECONDS` in `src/odoo_forge_docker/provider.py` and the Child #1 tests in `tests/adapters/test_docker_provider.py`; this restores the 180-second default without touching diagnostics, redaction, cleanup ownership, factory, public config, or the baseline harness. |

### Files Changed

| File | Change |
|---|---|
| `src/odoo_forge_docker/provider.py` | Changed the provider-owned default health wait from 180 to 300 seconds; retained constructor-only override and existing monotonic Docker-health polling. |
| `tests/adapters/test_docker_provider.py` | Added exact-default/override, unhealthy recovery, and retryable non-healthy-state tests using the existing fake clock and Docker boundary. |
| `openspec/changes/fix-odoo-factory-health-readiness/tasks.md` | Marked only 1.1, 1.2, and 2.1 complete. |

### Child #2 Remainder

Tasks 1.3–1.5, 2.2–2.3, and Phase 3 remain unchecked. Child #2 owns timeout diagnostics, inspect selection, bounded combined logs, redaction, malformed diagnostic fallbacks, and rollback evidence. No Child #2 production behavior or tests were implemented here.

### Delivery Boundary

- Strategy: forced feature-branch-chain.
- Child: #1, readiness deadline and recovery only; intended child PR base is the feature/tracker branch.
- Review budget: approximately 116 authored additions/deletions across provider, focused tests, task updates, and OpenSpec evidence; below 400 lines.

## Child #2 — Diagnostics, Redaction, and Runtime Acceptance

**Mode:** Strict TDD

### Completed Tasks

- [x] 1.3 Add RED tests for selected inspect fields, bounded combined logs before cleanup, and unavailable fallback markers.
- [x] 1.4 Add RED tests for resolved-secret and planned-environment-value redaction, including longest-first replacement.
- [x] 1.5 Prove created-only timeout rollback preserves reattached volumes, including incomplete container cleanup.
- [x] 2.2 Capture selected inspect state and `docker logs --tail 200` stdout/stderr before created-only rollback.
- [x] 2.3 Redact resolved credentials and all non-empty planned env values before diagnostic composition.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.3 / 2.2 | `tests/adapters/test_docker_provider.py` | Unit (fake Docker) | `uv run pytest tests/adapters/test_docker_provider.py -q` — 76 passed | New selected-inspect/combined-log and malformed-fallback tests failed: missing `final_health` sections and unavailable markers | Same command — 80 passed | Valid unhealthy inspect + stdout/stderr; malformed inspect + failed logs | Extracted one selected-field diagnostic path; direct wait helper behavior remains unchanged |
| 1.4 / 2.3 | Same | Unit (fake Docker + resolver) | Same 76-pass baseline | New resolver/planned-env diagnostic test failed: no redaction output | Same command — 80 passed | Resolved secret and every PostgreSQL/Odoo env value, including `database-value` / `database-value-suffix` ordering | Planned values are deduplicated and longest-first; existing injector redaction remains authoritative for resolved values |
| 1.5 | Same | Unit (fake Docker) | Existing created-only tests passed at baseline | Added incomplete-cleanup + reattached-volume approval test; it passed because created-only ownership was already correct | Same command — 80 passed | Existing new-resource removal plus reattached-volume preservation with cleanup incomplete | No provider ownership change needed; diagnostics do not alter `created` bookkeeping |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_docker_provider.py -q` — exit 0, **80 passed** in 2.38s. |
| Focused static check and exact result | `uv run ruff check src/odoo_forge_docker/provider.py tests/adapters/test_docker_provider.py` — exit 0, **All checks passed!** |
| Full suite | `uv run pytest -v` — exit 0, **535 passed, 1 deselected** in 3.66s. |
| Broader static/build checks | `uv run lint-imports` — exit 0, 6 contracts kept; `uv build` — exit 0. `uv run mypy` — exit 1 on pre-existing `tests/adapters/test_docker_provider_integration.py:75` (`BaseModel` has no attribute `labels`). |
| Runtime harness | `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` — exit 1 after 307.01s. Final redacted evidence: `final_health=unhealthy`, `FailingStreak=8`, `KeyError: 'ir.http'`, and missing `ir_module_module`; owned cleanup was attempted. Follow-up exact-name checks found no matching containers, network, or volumes. |
| Factory smoke | Not run: runtime acceptance failed; do not broaden to factory without user approval and contradictory diagnostics. |
| Rollback boundary | Revert Child #2 diagnostics/redaction code and Child #2 focused tests in `src/odoo_forge_docker/provider.py` and `tests/adapters/test_docker_provider.py`. This preserves Child #1's 300-second readiness/recovery behavior and leaves factory, public configuration, and the baseline harness untouched. |

### Files Changed

| File | Change |
|---|---|
| `src/odoo_forge_docker/provider.py` | Added selected timeout diagnostics, bounded combined Odoo logs, plan-value redaction, and safe unavailable markers before rollback. |
| `tests/adapters/test_docker_provider.py` | Added strict focused diagnostics, redaction, malformed-capture, ordering, and ownership-preservation coverage. |
| `openspec/changes/fix-odoo-factory-health-readiness/tasks.md` | Marked only Child #2 Phase 1/2 tasks complete. |

### Remaining / Blocked Tasks

- [ ] 3.1 Full verification remains unchecked because `uv run mypy` failed outside this Child's permitted files.
- [ ] 3.2 Runtime acceptance remains unchecked: unchanged real-Docker baseline is still unhealthy after 300 seconds.
- [ ] 3.3 Factory smoke remains intentionally unrun while 3.2 fails.

### Delivery Boundary

- Strategy: forced feature-branch-chain; Child #2 targets Child #1, never `main` directly.
- Review budget: 323 current provider/test additions/deletions before OpenSpec evidence; below the 400-line Child budget.
- No factory, harness, public configuration, branch, commit, staging, or PR changes were made.

## Child #3 — Fresh Database Bootstrap

**Mode:** Strict TDD

### Completed Tasks

- [x] 2.4 RED: exact shell-free bootstrap argv uses planned Odoo inputs without published ports.
- [x] 2.5 RED: bootstrap is new-Postgres-data-only; reused lifecycles skip it; collisions refuse before provisioning.
- [x] 2.6 RED: success removes bootstrap before normal Odoo; bootstrap failures are redacted, cleaned, and created-only rolled back.
- [x] 2.7 GREEN: provider executes and removes the temporary bootstrap before existing health readiness.
- [x] 2.8 REFACTOR: private explicit-argv bootstrap orchestration remains contract-neutral.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 2.4 | `tests/adapters/test_docker_provider.py` | Unit (fake Docker) | `uv run pytest tests/adapters/test_docker_provider.py -q` → 80 passed | Import of `_bootstrap_container_argv` failed before production code existed. | Focused suite → 86 passed. | Same planned image/network/env, secret-file mount, filestore/addon mounts, no detach/ports, and exact base-only args. | Extracted private foreground/portless argv builder; focused suite stayed green. |
| 2.5 | Same | Unit (fake Docker) | Same 80-pass baseline | Lifecycle/newness and collision scenarios were written before provider changes and blocked on the missing builder. | Focused suite → 86 passed. | New PG-data volume executes; reused volume skips; derived bootstrap identity collision rejects before network creation. | Kept volume-created fact internal to `_ensure_volume`; no plan/CLI/factory changes. |
| 2.6 / 2.7 | Same | Unit (fake Docker) | Same 80-pass baseline | Success-order, failed-output-redaction, and removal-failure cases were written before orchestration. | Focused suite → 86 passed. | Exit zero removal-before-normal; nonzero redacted cleanup; removal failure retries cleanup and prevents normal startup. | Bootstrap tracks separately in reverse created-resource order, then removes its tracking entry only after successful cleanup. |
| 2.8 | Same | Unit (fake Docker) | Focused suite → 86 passed | N/A — cleanup of GREEN code only. | Focused suite → 86 passed. | Existing readiness/diagnostics and new bootstrap paths both remain covered. | `ruff check` and targeted format check pass; no public-contract changes. |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/adapters/test_docker_provider.py -q` — exit 0, **86 passed** in 2.50s. |
| Full suite | `uv run pytest -v` — exit 0, **541 passed, 1 deselected** in 4.00s. |
| Static/build checks | `uv run lint-imports` — exit 0, 6 contracts kept; `uv build` — exit 0. `uv run mypy` — exit 1 on existing `tests/adapters/test_docker_provider_integration.py:75` (`BaseModel` has no attribute `labels`). Full `uv run ruff check` — exit 1 on existing integration-harness E501 at line 49 plus Child #3 formatting before targeted cleanup; final targeted `uv run ruff check src/odoo_forge_docker/provider.py tests/adapters/test_docker_provider.py` and targeted format check both exit 0. |
| Runtime harness command/scenario and exact result | `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` — exit 1 in 31.27s. `run -> status -> stop` reached the test's finally cleanup, then unchanged harness reported `owned cleanup failed: ['network rm odoo-forge-integration-real-e9048306a99a-real-e9048306a99a']`. Exact residual checks found no matching containers, network (`not found`), or volumes. This is a harness cleanup/idempotency defect; no factory run or unrelated fix was attempted. |
| Rollback boundary | Revert Child #3 changes in `src/odoo_forge_docker/provider.py` and `tests/adapters/test_docker_provider.py`; this removes only temporary fresh-volume bootstrap behavior and its tests while retaining Child #1/2 readiness and diagnostics. |

### Files Changed

| File | Change |
|---|---|
| `src/odoo_forge_docker/provider.py` | Added private foreground bootstrap argv, collision preflight, created-PG-volume authority, temporary container cleanup, redacted bounded failure evidence, and created-only rollback integration. |
| `tests/adapters/test_docker_provider.py` | Added strict-TDD bootstrap command, lifecycle, collision, success ordering, failure/redaction, cleanup, and regression coverage. |
| `openspec/changes/fix-odoo-factory-health-readiness/tasks.md` | Marked only 2.4–2.8 complete. |

### Remaining / Blocked Tasks

- [x] 3.1 is complete from the baseline's exact passing static/default-suite receipt: 541 passed, 4 deselected; mypy, Ruff, format, import boundaries, and build passed.
- [x] 3.2 is complete from the baseline's exact passing runtime receipt: 4 passed in 27.03s using the immutable factory digest, with `run -> status -> stop` and clean residual checks. The baseline acceptance depends on this bootstrap implementation; the earlier failed evidence above remains historical.
- [x] 3.3 is complete from the append-only factory-smoke receipt below; the earlier non-run status remains historical context for the prior Child #3 batch.

### Delivery Boundary

- Strategy: forced feature-branch-chain; Child #3 targets Child #2, never `main` directly.
- Review budget: approximately 230 authored Child #3 provider/test lines, below the 400-line budget; OpenSpec evidence is excluded from the code review slice.
- No factory, baseline harness, public configuration, branch, commit, staging, push, PR, or review changes were made.

## Phase 3 Acceptance Addendum — Factory Smoke and Correction Reconciliation

**Mode:** Strict TDD (evidence-only acceptance; no production or test behavior changed)

### Completed Tasks

- [x] 3.3 Run `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19`; record exact results while leaving factory and baseline harness unchanged.

### TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 3.3 | `factory/smoke-test.sh` | Factory real-Docker acceptance | Latest correction receipt retained below; no files modified | N/A — evidence-only execution of the pre-existing factory acceptance, not a new behavior | `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19` → exit 0, `==> SMOKE TEST PASSED: ghcr.io/aparragithub/odoo-ce:19` | N/A — one documented acceptance scenario | N/A — no code or test changed |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19` — exit 0; installed `base,sale,purchase,stock` into an ephemeral PostgreSQL database, then the normal server `/web/health` check passed: `==> SMOKE TEST PASSED: ghcr.io/aparragithub/odoo-ce:19`. |
| Runtime harness command/scenario and exact result | Same command — factory-created network, PostgreSQL, module-install container, and normal Odoo server completed successfully. The script's EXIT trap removed its generated `odoo-smoke-*` containers and network. Post-run `docker ps -a`, `docker network ls`, and `docker volume ls` filtered to `^odoo-smoke-` returned no residual names. |
| Docker/image receipt | Tag `ghcr.io/aparragithub/odoo-ce:19` resolved locally to image ID and repo digest `sha256:7403c677e133bd4dedf1ba600332deec2e45569d90db010def06853662ed1399`. Labels: source `https://github.com/aparragithub/odoo-forge`, version `19.0`, revision `65dbcabcd243abf24d6d3c3788d2caff66485790`, title `odoo-ce`. The tag remains intentionally mutable as recorded in the baseline SDD follow-up. |
| Rollback boundary | N/A — evidence-only completion changed no factory, production, or test behavior. Revert only this task checkbox and append-only acceptance receipt if the evidence record itself must be withdrawn. |

### Review Follow-up Reconciliation (Append-only)

The latest bounded correction verification is preserved here without replacing prior RED or failure receipts:

| Verification | Exact latest result |
|---|---|
| Provider focused suite | `uv run pytest tests/adapters/test_docker_provider.py -q` — exit 0, **87 passed**. |
| Harness helper suite | `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q -k 'cleanup or factory_image_resolves'` — exit 0, **4 passed, 1 deselected**. |
| Default suite | `uv run pytest -q` — exit 0, **542 passed, 5 deselected**. |
| Real Docker acceptance | `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` — exit 0, **5 passed in 26.42s**; `run -> status -> stop` and independent residual-name queries passed. |
| Static/build | `uv run mypy` — exit 0, success with no issues; `uv run ruff check` and `uv run ruff format --check` — exit 0; `uv run lint-imports` — exit 0, 6 contracts kept and 0 broken; `uv build` — exit 0. |

### Delivery Boundary

- Strategy: forced feature-branch-chain; this final evidence-only acceptance belongs after Child #3 and does not target `main` directly.
- Review budget: documentation-only task/progress receipt; no production, test, factory, or baseline-harness changes.
- Historical Child #2 and Child #3 failed runtime receipts remain above unchanged for auditability.
