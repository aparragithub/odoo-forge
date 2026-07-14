```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:c20f9bc2d72c23b99fb1f0493b3411b5249cabdd232e09b3049fba8c926165c1
verdict: pass
blockers: 0
critical_findings: 0
requirements: 3/3
scenarios: 8/8
test_command: uv run pytest
test_exit_code: 0
test_output_hash: sha256:061031b9d26467399d55f709b7f61566ebace0117310c6f84b78c5416a49c518
build_command: uv build
build_exit_code: 0
build_output_hash: sha256:d775495c957a15a2bc6d9669ec153491058e9c1e8c1ce8d505b0070a537092c2
```

## Verification Report

**Change**: `fix-odoo-factory-health-readiness`  
**Version**: N/A  
**Mode**: Strict TDD  
**Artifact store**: OpenSpec  
**Execution**: Interactive, independent final requirements/runtime verification  
**Final verdict**: **PASS**

### Executive Summary

The current implementation satisfies all 3 delta requirements and all 8 scenarios. All 16 tasks are complete; focused provider tests, the default suite, real-Docker lifecycle, factory smoke, coverage, static checks, build, and independent residual queries passed from the current workspace.

Provider-owned bootstrap uses invocation-proven Postgres-volume creation, token verification for volume-race safety, cidfile identity for timeout/exception cleanup, base-only foreground initialization, created-only rollback, a 300-second readiness deadline, and bounded redacted diagnostics. Review lineage `review-e4e6c177120705ff` remains approved and content-bound to candidate tree `0371e507b834fe6683d44ccb22ddc1bab3dee596`.

### Completeness

| Metric | Value |
|---|---:|
| Requirements total / compliant | 3 / 3 |
| Scenarios total / compliant | 8 / 8 |
| Tasks total / complete / incomplete | 16 / 16 / 0 |
| Runtime acceptance commands passed | 2 / 2 |
| Static/build commands passed | 5 / 5 |

### Review Receipt Binding

`gentle-ai review validate --gate post-apply --cwd /home/aparra/Desarrollo/odoo-forge --lineage review-e4e6c177120705ff` exited 0 with `result=allow`: authoritative transaction, repository target, and content-bound artifacts match.

| Field | Bound value |
|---|---|
| Lineage | `review-e4e6c177120705ff` |
| Generation / state | `1` / `approved` |
| Authority/store revision | `sha256:5020610194ba2016e95e3277398886bd13a5f635f048b119e19b60840fec2f96` |
| Receipt hash | `sha256:70a0a19954c2a0b3dfdd637e92b4149bd1410daea11ae00ad1f8f53659f293c4` |
| Base tree | `504016f00d3cf628bbfc4c583936c9027378981f` |
| Final candidate tree | `0371e507b834fe6683d44ccb22ddc1bab3dee596` |
| Paths digest | `sha256:712d84e27f4f008934d8ff4e2eb545fecffbb12fd426b525784273a8519dcdc5` |
| Fix delta hash | `sha256:faa842edd3b7385af3f2f82b69742e89a6b2c65a3ef4a6693c7f7eb1a2981889` |
| Review evidence hash | `sha256:8b64683fb24be4fac628ea15b602692197f4b9fcaac7107cb986ac64f710446e` |
| Receipt terminal state | `approved` |

The receipt resolves findings `R2-001`, `R2-002`, `R3-001`, `R3-002`, and `R4-001`. Current tests independently re-proved token-verified volume ownership and cidfile-based bootstrap cleanup.

### Build and Test Execution

| Command | Exit | Exact result | Output SHA-256 |
|---|---:|---|---|
| `uv run pytest tests/adapters/test_docker_provider.py -q` | 0 | 90 passed in 2.46s | `faf802d24fe6a6e949e89c6e510aa46f91919b755482344461025805483bd515` |
| `uv run pytest` | 0 | 545 passed, 6 deselected in 3.72s; configured aggregate coverage 98% | `061031b9d26467399d55f709b7f61566ebace0117310c6f84b78c5416a49c518` |
| `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` | 0 | 6 passed in 27.59s | `142b7f9ebd42f09e71f81589674ac853beac9cbda0b455f4fc9517645debe643` |
| `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19` | 0 | Base/sale/purchase/stock install and normal-server HTTP health passed; `SMOKE TEST PASSED` | `d3d52741e97ba7d8b1052603541d0bb77b89e0b6d59037a6bfa4358ffabac804` |
| `uv run pytest tests/adapters/test_docker_provider.py -q --cov=odoo_forge_docker.provider --cov-branch --cov-report=term-missing` | 0 | 90 passed; changed production file 96% combined line/branch coverage | `a8c03dd5dc1dd5863182bf9ba6f4832a2cd1184589e4b8c798d9c0ff476e8121` |
| `uv run ruff check` | 0 | All checks passed | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff format --check` | 0 | 108 files already formatted | `1a9301f4cf03fa0d5c4d8f77f50252de3a09f3dbe30fd813f1131981eceb1770` |
| `uv run mypy` | 0 | No issues in 105 source files | `a7c4aae49ff9d21cbf4edf1b955366f4cb545b2dbf41b63329a9f1c16b3b0c5d` |
| `uv run lint-imports` | 0 | 6 contracts kept, 0 broken | `2ec1151949b927abca48266b58cbd6caa54de49983e2f193d09d1b7230643333` |
| `uv build` | 0 | sdist and wheel built | `d775495c957a15a2bc6d9669ec153491058e9c1e8c1ce8d505b0070a537092c2` |
| Independent Docker residual queries for `odoo-forge-integration-real-` and `odoo-smoke-` containers, networks, and volumes | 0 | All six result sets empty | `7bde5ffafe0bcdea9102e8b089b49f29a278ad8d8fc92ff9a6d6dd25cca982fe` |

### Spec Compliance Matrix

| Requirement | Scenario | Runtime covering evidence | Result |
|---|---|---|---|
| `run()` provisions its own Postgres when none is external | New lifecycle bootstraps before normal Odoo | `test_run_bootstraps_only_new_postgres_data_before_normal_odoo`; real-Docker round trip | ✅ COMPLIANT |
| Same | Existing lifecycle is not repaired | `test_run_does_not_bootstrap_reused_postgres_data_lifecycle`; `test_volume_create_race_does_not_bootstrap_or_delete_foreign_volume` | ✅ COMPLIANT |
| Same | Bootstrap failure rolls back owned resources | Failure/redaction, cidfile timeout/exception, name-race, and removal-failure tests | ✅ COMPLIANT |
| Same | Bootstrap identity collision fails safely | `test_run_refuses_bootstrap_name_collision_before_provisioning`; conflict-race test | ✅ COMPLIANT |
| Same | Unhealthy normal server recovers before deadline | `test_odoo_health_wait_recovers_from_unhealthy_before_deadline`; retry parametrization | ✅ COMPLIANT |
| Bootstrap and readiness diagnostics are secret-safe | Bootstrap failure reports safe evidence | `test_bootstrap_failure_redacts_output_removes_temporary_container_and_rolls_back` | ✅ COMPLIANT |
| Same | Readiness timeout retains completed defenses | Selected-inspect/bounded-log, fallback-marker, redaction, and ownership tests | ✅ COMPLIANT |
| Factory, ownership, and acceptance contracts remain unchanged | Unchanged harness proves the lifecycle | 6-test real-Docker run, factory smoke, and independent empty residual queries | ✅ COMPLIANT |

**Compliance summary**: 8/8 scenarios compliant at runtime.

### Requirement Correctness

| Requirement | Static implementation evidence | Status |
|---|---|---|
| Provider-owned fresh bootstrap | `_ensure_volume` returns newness only after a unique create-token label is observed; `run` bootstraps only on that fact; bootstrap argv is foreground, portless, shell-free, and base-only. | ✅ Implemented |
| Ownership and race safety | Existing volumes return false; post-create label mismatch suppresses ownership/bootstrap/deletion; rollback tracks only proven-created resources in reverse order. | ✅ Implemented |
| Cidfile timeout cleanup | Bootstrap uses `--cidfile`; timeout/transport exceptions append immutable container identity before rollback; name-collision paths never delete by unowned name. | ✅ Implemented |
| 300-second readiness | Default is 300 seconds; monotonic polling treats all non-healthy states as recoverable until deadline and accepts the final budgeted probe. | ✅ Implemented |
| Diagnostics and redaction | Final health, selected state, and `docker logs --tail 200` are captured before rollback; resolved secrets and non-empty planned values are redacted longest-first. | ✅ Implemented |
| Failure and rollback | Bootstrap failure prevents normal Odoo; success removes bootstrap before normal startup; cleanup failures preserve the primary cause and append residual identities. | ✅ Implemented |
| Public/factory stability | Git diff has no paths under `factory`, `src/odoo_forge_cli`, `src/odoo_forge/backend`, or `src/odoo_forge/manifest`; protocol-signature tests pass. | ✅ Preserved |
| Real lifecycle | Fresh bootstrap, Docker-health readiness, `run -> status -> stop`, volume preservation, final cleanup, factory smoke, and residual absence passed. | ✅ Proven |

### Task Coverage

| Task | Verification evidence | Status |
|---|---|---|
| 1.1 | Default 300 seconds plus explicit override test | ✅ |
| 1.2 | Unhealthy, missing, malformed, unknown, and starting recovery tests | ✅ |
| 1.3 | Selected inspect, bounded combined logs, fallback-marker tests | ✅ |
| 1.4 | Resolved-secret and all planned-value redaction test | ✅ |
| 1.5 | Reattached-volume preservation with incomplete cleanup test | ✅ |
| 2.1 | Provider constant and current focused execution | ✅ |
| 2.2 | Diagnostics-before-rollback ordering and content tests | ✅ |
| 2.3 | Longest-first redaction behavior and no-secret assertions | ✅ |
| 2.4 | Exact bootstrap argv/timeout/ports/mounts/secrets/base-only test | ✅ |
| 2.5 | New/reused lifecycle, collision, and volume-race tests | ✅ |
| 2.6 | Success order, nonzero, timeout/exception, removal failure, rollback tests | ✅ |
| 2.7 | Focused provider suite plus real-Docker bootstrap lifecycle | ✅ |
| 2.8 | Private API/static checks and public protocol conformance tests | ✅ |
| 3.1 | Default suite, Ruff, format, mypy, import contracts, build | ✅ |
| 3.2 | Real-Docker integration: 6 passed; independent residuals empty | ✅ |
| 3.3 | Factory smoke passed; independent smoke residuals empty | ✅ |

### Design Coherence

| Decision | Followed? | Evidence |
|---|---|---|
| Postgres-data creation is newness authority | ✅ Yes | Token-verified `_ensure_volume` result controls bootstrap. |
| Bootstrap only `base` with planned runtime contract | ✅ Yes | Exact argv and real-Docker execution passed. |
| Derived bootstrap identity; refuse collisions | ✅ Yes | Preflight and post-preflight race tests passed. |
| Remove bootstrap before normal server | ✅ Yes | Ordering assertions and real lifecycle passed. |
| Preserve 300-second health and diagnostics defenses | ✅ Yes | Focused deadline, recovery, diagnostics, and redaction tests passed. |
| Created-only reverse rollback | ✅ Yes | Unit ownership tests and empty real-Docker residual checks passed. |
| No public/factory behavior changes | ✅ Yes | Scoped diff check was empty; public protocol/static checks passed. |

The working candidate also contains the separately planned `stabilize-real-docker-baseline` harness work and both SDD roots are included in the approved review snapshot. The baseline harness is therefore used as external acceptance evidence, not attributed as an implementation change of this delta.

### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | Apply progress contains Strict-TDD evidence tables for all three implementation slices. |
| Implementation tasks have tests | ✅ | 13/13 behavioral implementation tasks map to current focused tests. |
| RED confirmed | ✅ | Reported test file exists; historical failures/approval characterizations are preserved. |
| GREEN confirmed | ✅ | Current focused provider suite: 90/90 passed. |
| Triangulation adequate | ✅ | Happy, reused, collision, race, nonzero, timeout, exception, removal, unhealthy recovery, malformed diagnostics, redaction, and residual paths vary inputs and outcomes. |
| Safety net for modified behavior | ✅ | Each implementation slice records a passing focused baseline before provider changes. |

**TDD compliance**: 6/6 checks passed. Apply progress has explicit rows covering all 13 implementation tasks and task 3.3; tasks 3.1 and 3.2 are execution-only acceptance gates, so RED/GREEN rows are not applicable. Their required commands were independently rerun here.

### Test Layer Distribution

| Layer | Tests | Files | Tool/boundary |
|---|---:|---:|---|
| Unit / provider integration with fake Docker | 90 | 1 | pytest, monkeypatch, fake clock/router |
| Real-Docker integration | 6 | 1 | pytest against live Docker daemon |
| Factory acceptance | 1 command | 1 script | real Docker, module install, HTTP health |
| Browser E2E | 0 | 0 | Not applicable |

### Changed File Coverage

| File | Combined line/branch coverage | Uncovered lines/branches | Rating |
|---|---:|---|---|
| `src/odoo_forge_docker/provider.py` | 96% | 278-279, 306→exit, 334, 381→383, 422, 446, 504→508, 517-518, 558, 561-562 | ✅ Excellent |

The default configured coverage source is only `odoo_forge`; a dedicated current run explicitly added `odoo_forge_docker.provider` to obtain changed-production-file coverage. Test files are not production coverage targets.

### Assertion Quality

Both changed test files were inspected in full. Tests call production or harness code and assert concrete argv, ordering, error, ownership, state, cleanup, redaction, and residual outcomes. No tautologies, production-free assertions, ghost loops, smoke-only assertions, or mock-heavy anti-patterns were found.

**Assertion quality**: ✅ All assertions verify real behavior; 0 CRITICAL, 0 WARNING.

### Quality Metrics

**Linter**: ✅ Ruff check passed  
**Formatter**: ✅ Ruff format check passed  
**Type checker**: ✅ mypy passed  
**Architecture**: ✅ 6 import contracts kept, 0 broken  
**Build**: ✅ sdist and wheel built  
**Diff hygiene**: ✅ `git diff --check` passed

### Residuals and Limitations

- Independent post-run Docker queries found no integration or smoke containers, networks, or volumes.
- The real-Docker test resolves the mutable tag to a validated immutable local repo digest before lifecycle execution; registry-side tag mutability remains outside this change.
- The approved review records a non-blocking baseline dependency follow-up: the harness's target-name plus `not found` substring classification can be made stricter. It belongs to `stabilize-real-docker-baseline`, did not invalidate this change's runtime result, and is not a blocker here.
- Proposal success-criteria checkboxes remain unchecked even though tasks, runtime evidence, and this final verification prove all four outcomes. This is artifact-hygiene only and does not contradict executable evidence.

### Issues Found

**CRITICAL**: None.  
**WARNING**: None.  
**SUGGESTION**: Reconcile the proposal success-criteria checkboxes when archival tooling synchronizes the completed change; do not alter implementation or acceptance evidence.

### Canonical Verification Evidence Bytes

The following single JSON line, including its terminating newline, is the exact canonical evidence preimage whose SHA-256 is the envelope `evidence_revision`:

```json
{"build":{"command":"uv build","exit_code":0,"output_hash":"sha256:d775495c957a15a2bc6d9669ec153491058e9c1e8c1ce8d505b0070a537092c2"},"change":"fix-odoo-factory-health-readiness","commands":[{"command":"uv run pytest tests/adapters/test_docker_provider.py -q","exit_code":0,"output_hash":"sha256:faf802d24fe6a6e949e89c6e510aa46f91919b755482344461025805483bd515"},{"command":"uv run pytest","exit_code":0,"output_hash":"sha256:061031b9d26467399d55f709b7f61566ebace0117310c6f84b78c5416a49c518"},{"command":"ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q","exit_code":0,"output_hash":"sha256:142b7f9ebd42f09e71f81589674ac853beac9cbda0b455f4fc9517645debe643"},{"command":"./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19","exit_code":0,"output_hash":"sha256:d3d52741e97ba7d8b1052603541d0bb77b89e0b6d59037a6bfa4358ffabac804"},{"command":"uv run pytest tests/adapters/test_docker_provider.py -q --cov=odoo_forge_docker.provider --cov-branch --cov-report=term-missing","exit_code":0,"output_hash":"sha256:a8c03dd5dc1dd5863182bf9ba6f4832a2cd1184589e4b8c798d9c0ff476e8121"},{"command":"uv run ruff check","exit_code":0,"output_hash":"sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18"},{"command":"uv run ruff format --check","exit_code":0,"output_hash":"sha256:1a9301f4cf03fa0d5c4d8f77f50252de3a09f3dbe30fd813f1131981eceb1770"},{"command":"uv run mypy","exit_code":0,"output_hash":"sha256:a7c4aae49ff9d21cbf4edf1b955366f4cb545b2dbf41b63329a9f1c16b3b0c5d"},{"command":"uv run lint-imports","exit_code":0,"output_hash":"sha256:2ec1151949b927abca48266b58cbd6caa54de49983e2f193d09d1b7230643333"},{"command":"independent Docker residual queries for integration and smoke prefixes","exit_code":0,"output_hash":"sha256:7bde5ffafe0bcdea9102e8b089b49f29a278ad8d8fc92ff9a6d6dd25cca982fe"}],"requirements":{"complete":3,"total":3},"review":{"authority_revision":"sha256:5020610194ba2016e95e3277398886bd13a5f635f048b119e19b60840fec2f96","candidate_tree":"0371e507b834fe6683d44ccb22ddc1bab3dee596","gate":"post-apply","lineage":"review-e4e6c177120705ff","result":"allow"},"scenarios":{"complete":8,"total":8},"schema":"gentle-ai.verification-evidence/v1","tasks":{"complete":16,"total":16},"test":{"command":"uv run pytest","exit_code":0,"output_hash":"sha256:061031b9d26467399d55f709b7f61566ebace0117310c6f84b78c5416a49c518"},"verdict":"pass"}
```

### Verdict and Archive Safety

**PASS** — requirements 3/3, scenarios 8/8, tasks 16/16, blockers 0, critical findings 0.

**Archive safe**: **Yes**, subject to the native archive gate revalidating this exact passing envelope and the already-approved lineage. No implementation, test, planning, factory, public-contract, Git-index, commit, branch, push, PR, archive, or review action was performed by verification.

### Result Contract

```yaml
status: success
executive_summary: Independent Strict-TDD verification passed all requirements, scenarios, tasks, runtime acceptance, static checks, build, review binding, and residual checks.
artifacts:
  - openspec/changes/fix-odoo-factory-health-readiness/verify-report.md
next_recommended: archive
risks: No blocking risk; mutable-tag handling and the baseline harness not-found classifier remain external non-blocking dependency context.
skill_resolution: paths-injected
```
