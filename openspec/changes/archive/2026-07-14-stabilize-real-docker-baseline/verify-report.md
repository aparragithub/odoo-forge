```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:323d41a60eaf452c3180adf47ac1d1591665a4b41e0111f7c687ee207fb3765f
verdict: pass
blockers: 0
critical_findings: 0
requirements: 1/1
scenarios: 13/13
test_command: uv run pytest
test_exit_code: 0
test_output_hash: sha256:abadf38d98e01c5e72a64457c2b1039f0184fcf58a97ad40405e0b7cc0782766
build_command: uv build
build_exit_code: 0
build_output_hash: sha256:d775495c957a15a2bc6d9669ec153491058e9c1e8c1ce8d505b0070a537092c2
```

## Verification Report

**Change**: `stabilize-real-docker-baseline`  
**Version**: N/A  
**Mode**: Strict TDD  
**Artifact store**: OpenSpec  
**Execution**: Interactive, independent requirements/runtime verification  
**Final verdict**: **PASS**

### Executive Summary

The current workspace satisfies the delta's single requirement, all 13 scenarios, and all 19 tasks. Independent execution passed the focused helper and provider suites, default daemon-independent suite, six-test real-Docker lifecycle, factory smoke, provider coverage, static checks, build, review gate, and post-run residual queries.

The accepted readiness fix is present in the current provider and synchronized canonical `local-backend` spec. The real-Docker run independently proved that provider-owned fresh bootstrap completes before healthy normal Odoo, after which `run -> status -> stop`, volume preservation, exact test cleanup, and fail-closed residual checks succeed.

### Completeness

| Metric | Value |
|---|---:|
| Requirements total / compliant | 1 / 1 |
| Scenarios total / compliant | 13 / 13 |
| Tasks total / complete / incomplete | 19 / 19 / 0 |
| Focused/default/integration/factory commands passed | 4 / 4 |
| Static/build commands passed | 6 / 6 |
| Blockers / critical findings | 0 / 0 |

### Review Receipt Binding

`gentle-ai review validate --gate post-apply --cwd /home/aparra/Desarrollo/odoo-forge --lineage review-a49dc58752713b78` exited 0 with `result=allow`: the authoritative transaction, current repository target, and content-bound artifacts match.

| Field | Bound value |
|---|---|
| Lineage | `review-a49dc58752713b78` |
| Generation / gate result | `1` / `allow` |
| Authority/store revision | `sha256:808537a52e707154698ac8e9999d7279d5889ef3f152e30a6aa719e6f994e34d` |
| Base tree | `504016f00d3cf628bbfc4c583936c9027378981f` |
| Candidate tree | `aefce973f78cf8af7da01f65440b02540d315ff2` |
| Paths digest | `sha256:d2b2fbb7e0585622941dd7ccc0d811809e3f3797b1b0dc6ae6d75c360ff1cd0d` |
| Fix delta hash | `sha256:efa8ab487d418f0c26f09741c6c85f567abaed2352fed65be1c9d3fc5884ad71` |
| Validation output hash | `sha256:22a53d67520d6f0d1d4154367970022952016f7fd09c82e9e9be0f05911ca59b` |

### Build and Test Execution

Output hashes cover the normalized captured stdout/stderr bytes shown by each execution, including one terminating newline.

| Command | Exit | Exact result | Output SHA-256 |
|---|---:|---|---|
| `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q -k 'cleanup or factory_image_resolves'` | 0 | 4 passed, 2 deselected in 0.39s | `b3981960585f9570cdc37de5001cc138357e4c61932137ab0d77ad149e249c41` |
| `uv run pytest tests/adapters/test_docker_provider.py -q` | 0 | 90 passed in 2.49s | `c617a2c5dd40eee74c30106106ba9352ccf3bfcb2816cf5f8f62df2d0704b289` |
| `env -u ODOO_FORGE_TEST_ODOO_IMAGE uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` | 1 (expected) | 5 passed, 1 failed in 0.53s; after Docker detection, missing image selection failed rather than skipped | `da900e253fe727b6be2a3b513503bd5eff8eafe375ad9c3f9eb1d79c4177a427` |
| `uv run env PATH=/nonexistent /home/aparra/Desarrollo/odoo-forge/.venv/bin/python -m pytest -m integration tests/adapters/test_docker_provider_integration.py -q` | 0 | 5 passed, 1 skipped in 0.31s; missing Docker executable produced the declared prerequisite skip | `26a8c0cebd8d31531e2d6d80d38d0a4d997471b06d11d56c62a1dcb615aaa478` |
| `uv run pytest` | 0 | 545 passed, 6 deselected in 3.62s; configured aggregate coverage 98% | `abadf38d98e01c5e72a64457c2b1039f0184fcf58a97ad40405e0b7cc0782766` |
| `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` | 0 | 6 passed in 28.45s | `ee769c0dc4dddf9f0dc472891ab0bcff30344cd9d653aa3f10186412a9177046` |
| `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19` | 0 | Base/sale/purchase/stock install and normal-server HTTP health passed; `SMOKE TEST PASSED` | `9bb04d8f814e2d473ea53ef32b8378051516556d0b6aa6c6b4b5093c62f2ba49` |
| `uv run pytest tests/adapters/test_docker_provider.py -q --cov=odoo_forge_docker.provider --cov-branch --cov-report=term-missing` | 0 | 90 passed; provider combined line/branch coverage 96% | `5e86eb9877c767172ec437dc4f92c3b402a70e7339efa6064e5302063d1e63dd` |
| `uv run ruff check` | 0 | All checks passed | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `uv run ruff format --check` | 0 | 108 files already formatted | `1a9301f4cf03fa0d5c4d8f77f50252de3a09f3dbe30fd813f1131981eceb1770` |
| `uv run mypy` | 0 | No issues in 105 source files | `a7c4aae49ff9d21cbf4edf1b955366f4cb545b2dbf41b63329a9f1c16b3b0c5d` |
| `uv run lint-imports` | 0 | 6 contracts kept, 0 broken | `2ec1151949b927abca48266b58cbd6caa54de49983e2f193d09d1b7230643333` |
| `uv build` | 0 | sdist and wheel built | `d775495c957a15a2bc6d9669ec153491058e9c1e8c1ce8d505b0070a537092c2` |
| `git diff --check` | 0 | No whitespace errors | `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b` |
| Independent integration/smoke container, network, and volume queries | 0 | All six result sets empty | `7bde5ffafe0bcdea9102e8b089b49f29a278ad8d8fc92ff9a6d6dd25cca982fe` |

Docker client/server was `29.6.1/29.6.1`. The selected image reported source `https://github.com/aparragithub/odoo-forge`, version `19.0`, revision `65dbcabcd243abf24d6d3c3788d2caff66485790`, and matching immutable digest `ghcr.io/aparragithub/odoo-ce@sha256:7403c677e133bd4dedf1ba600332deec2e45569d90db010def06853662ed1399`.

### Spec Compliance Matrix

| Requirement | Scenario | Passing runtime evidence | Result |
|---|---|---|---|
| Real-Docker baseline provides opt-in lifecycle evidence | Prerequisites are unavailable | PATH-isolated pytest run: 5 passed, 1 prerequisite skip | ✅ COMPLIANT |
| Same | Prerequisites are available | Missing-selector command failed after Docker detection; selected-image run passed | ✅ COMPLIANT |
| Same | Required images and identity are used | Factory metadata/digest helper plus real lifecycle; `postgres:16`; UUID identity labels | ✅ COMPLIANT |
| Same | Secrets remain safe | `_plan` and exception assertions; real run emitted no generated secret | ✅ COMPLIANT |
| Same | Host ports are collision-resistant | Real lifecycle asserted non-empty inspected mappings for 8069 and 8072 from `None` plan ports | ✅ COMPLIANT |
| Same | Readiness is bounded | Provider suite covers bounded PG/Odoo waits and timeout diagnostics; real lifecycle reached both gates | ✅ COMPLIANT |
| Same | Run, status, and stop complete | Six-test real-Docker command completed `run -> status -> stop` | ✅ COMPLIANT |
| Same | Stop preserves lifecycle volumes | Real test observed absent containers/network and both named volumes present after `stop` | ✅ COMPLIANT |
| Same | Cleanup is ownership-scoped | Helper tests cover absent resources and true errors; real `finally` cleanup includes bootstrap and exact plan names | ✅ COMPLIANT |
| Same | Residual checks are independent | Query-failure helper is fail-closed; real label queries and external prefix queries were empty | ✅ COMPLIANT |
| Same | The default suite remains daemon-independent | `uv run pytest`: 545 passed, 6 integration tests deselected | ✅ COMPLIANT |
| Same | Verification records evidence | This report records versions, image identity, exact commands/results/hashes, lifecycle, preservation, cleanup, and residuals | ✅ COMPLIANT |
| Same | Production defects are extracted | Historical readiness failure was retained and fixed through the separately archived change; baseline assertions were not weakened | ✅ COMPLIANT |

**Compliance summary**: 13/13 scenarios compliant with current passing runtime evidence.

### Requirement Correctness

| Area | Static and runtime evidence | Status |
|---|---|---|
| Prerequisite boundary | `_require_docker` skips only missing executable or nonzero daemon-info; image selection begins afterward and asserts failures | ✅ Implemented |
| Factory image trust | `_factory_image` validates source/version/revision before `_immutable_digest` selects a repository-matching digest | ✅ Implemented |
| Provider bootstrap dependency | Current `run` bootstraps `base` only when token-verified PG-data creation proves a fresh lifecycle; real run passed | ✅ Proven |
| Secret safety | Opaque handles and `SopsEnvFileInjector` keep generated credentials out of plan repr and command evidence; provider diagnostics redact values | ✅ Implemented |
| Ephemeral ports/readiness | Odoo ports are planned as `None`; inspected host mappings are asserted; provider deadlines are bounded | ✅ Proven |
| Lifecycle and preservation | Live status is Docker-derived; `stop` removes containers/network but never named volumes | ✅ Proven |
| Cleanup and residuals | Exact test-owned names include the bootstrap container; cleanup accumulates real errors; residual query failures become residual findings | ✅ Implemented |
| Canonical readiness synchronization | Canonical `openspec/specs/local-backend/spec.md` contains all 3 accepted readiness requirements and 8 scenarios from the archived delta | ✅ Synchronized |
| Default isolation | `pyproject.toml` excludes `integration`; explicit `-m integration` is required | ✅ Preserved |

### Task Coverage

| Task | Verification evidence | Status |
|---|---|---|
| 1.1 | Integration marker plus default six-test deselection | ✅ |
| 1.2 | Missing-Docker skip and missing-selector expected failure | ✅ |
| 1.3 | Factory labels/digest test, real image receipt, `postgres:16` assertion | ✅ |
| 1.4 | UUID identity, `tmp_path`, ephemeral ports, in-memory credentials | ✅ |
| 2.1 | Secret assertions and unconditional `finally` cleanup | ✅ |
| 2.2 | Provider readiness suite and real successful startup | ✅ |
| 2.3 | Live `run -> status -> stop` execution | ✅ |
| 2.4 | Post-stop absence and volume-preservation assertions | ✅ |
| 3.1 | Absent/permission/unrelated-error cleanup tests and real cleanup | ✅ |
| 3.2 | Query-failure test and empty independent residual queries | ✅ |
| 3.3 | Current default, integration, static, image, Docker, cleanup, and residual evidence | ✅ |
| 3.4 | Separate archived readiness fix retained; no baseline assertion weakening | ✅ |
| 4.1 | Three cleanup classifier behaviors passed | ✅ |
| 4.2 | Typed `_inspect_labels`; mypy passed | ✅ |
| 4.3 | Ruff and formatter passed | ✅ |
| 4.4 | Validated tag resolves to matching immutable digest before planning/pull | ✅ |
| 5.1 | Focused helper and provider suites passed | ✅ |
| 5.2 | Default suite, Ruff, format, mypy, import contracts, and build passed | ✅ |
| 5.3 | Exact real-Docker command passed; no owned residuals remained | ✅ |

### Design Coherence

| Decision | Followed? | Evidence |
|---|---|---|
| Direct provider boundary | ✅ Yes | Harness invokes `DockerBackendProvider` without CLI expansion. |
| Validate factory image, then use immutable digest | ✅ Yes | Source/version/revision validation precedes digest resolution; real receipt matches. |
| No baseline production seam | ✅ Yes | Baseline behavior remains in the integration harness; current production changes belong to the archived readiness prerequisite. |
| Exact cleanup, never prune | ✅ Yes | Cleanup names only plan containers, bootstrap, network, and volumes. |
| Opt-in Docker execution | ✅ Yes | Default suite deselected all six integration tests. |
| Secret-safe generated fixture | ✅ Yes | Opaque handles, in-memory resolver, redaction assertions, no secret in evidence. |
| Ephemeral ports and bounded readiness | ✅ Yes | Real mappings and provider deadlines were exercised. |
| Stop preservation before final deletion | ✅ Yes | Real assertions distinguish preserved lifecycle volumes from final test-owned cleanup. |
| Defect extraction | ✅ Yes | Readiness defect remained a separate archived SDD change and supplies the provider prerequisite. |

### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | `apply-progress.md` retains historical failures and reconciled RED/GREEN evidence. |
| All tasks have tests or execution gates | ✅ | 19/19 tasks map to current tests, static checks, or explicit acceptance commands. |
| RED confirmed | ✅ | Modified test file exists; historical missing-selector, readiness, cleanup, typing, lint, and mutable-tag failures remain recorded. |
| GREEN confirmed | ✅ | Current helper, provider, default, and real-Docker executions all passed. |
| Triangulation adequate | ✅ | Six integration-marked tests vary absent cleanup, real cleanup error, unrelated error, failed queries, digest resolution, and live lifecycle. |
| Safety net for modified file | ✅ | The original skipped baseline and later failing receipts are preserved before the passing reconciliation. |

**TDD compliance**: 6/6 checks passed. Historical RED states were not recreated destructively; current GREEN and triangulation were independently executed.

### Test Layer Distribution

| Layer | Tests | Files | Boundary |
|---|---:|---:|---|
| Harness helper tests | 5 | 1 | pytest with monkeypatched Docker subprocess helper |
| Provider tests with fake Docker | 90 | 1 | pytest with subprocess router/fake clock |
| Real-Docker lifecycle | 1 | 1 | live Docker daemon |
| Factory acceptance | 1 command | 1 script | live Docker, module install, HTTP health |
| Browser E2E | 0 | 0 | Not applicable |

### Changed File Coverage

The baseline implementation file is a test artifact, so production coverage is not assigned to it. The separately archived provider prerequisite was nevertheless rerun with explicit coverage:

| File | Combined line/branch coverage | Uncovered lines/branches | Rating |
|---|---:|---|---|
| `src/odoo_forge_docker/provider.py` | 96% | 278-279, 306→exit, 334, 381→383, 422, 446, 504→508, 517-518, 558, 561-562 | ✅ Excellent |

### Assertion Quality

The complete baseline test file was inspected. Every test calls harness or production behavior and asserts concrete failures, cleanup results, digest output, lifecycle state, inspected port mappings, preservation, or residual absence. Fixed-size resource tuples prevent ghost-loop behavior; no tautologies, production-free assertions, type-only assertions, smoke-only assertions, or mock-heavy anti-patterns were found.

**Assertion quality**: ✅ All assertions verify real behavior; 0 CRITICAL, 0 WARNING.

### Quality Metrics

**Linter**: ✅ Ruff passed  
**Formatter**: ✅ 108 files formatted  
**Type checker**: ✅ mypy passed  
**Architecture**: ✅ 6 import contracts kept  
**Build**: ✅ sdist and wheel built  
**Diff hygiene**: ✅ `git diff --check` passed

### Issues Found

**CRITICAL**: None.  
**WARNING**: None.  
**SUGGESTION**: The approved review's existing cleanup-classifier follow-up still applies. At `tests/adapters/test_docker_provider_integration.py:252`, `_cleanup` accepts any stderr containing the exact target name followed by `not found`; this is narrower than a broad `not found` match and the current unrelated-error test passes, but structured Docker error classification would be stricter. It is non-blocking because real cleanup passed, query failures fail closed, and independent residual result sets were empty.

### Limitations and Residuals

- The missing-executable prerequisite branch was executed in a PATH-isolated pytest process. The adjacent unreachable-daemon branch is source-equivalent after `docker info` returns nonzero but was not induced against the active daemon.
- The selected local tag was validated and resolved to a matching immutable local repo digest before planning. Registry-side future tag mutation remains outside this evidence.
- Strict-TDD historical RED chronology is preserved in `apply-progress.md`; verification reran current behavior rather than altering the workspace to recreate old defects.
- The OpenSpec CLI is not installed, so canonical synchronization was checked by direct artifact comparison and current heading/scenario content rather than an OpenSpec CLI validator.
- Independent post-run queries found no integration or smoke containers, networks, or volumes.

### Canonical Verification Evidence Bytes

The following single JSON line, including its terminating newline, is the exact canonical evidence preimage whose SHA-256 is the envelope `evidence_revision`:

```json
{"build":{"command":"uv build","exit_code":0,"output_hash":"sha256:d775495c957a15a2bc6d9669ec153491058e9c1e8c1ce8d505b0070a537092c2"},"change":"stabilize-real-docker-baseline","commands":[{"command":"uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q -k 'cleanup or factory_image_resolves'","exit_code":0,"output_hash":"sha256:b3981960585f9570cdc37de5001cc138357e4c61932137ab0d77ad149e249c41"},{"command":"uv run pytest tests/adapters/test_docker_provider.py -q","exit_code":0,"output_hash":"sha256:c617a2c5dd40eee74c30106106ba9352ccf3bfcb2816cf5f8f62df2d0704b289"},{"command":"env -u ODOO_FORGE_TEST_ODOO_IMAGE uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q","exit_code":1,"expected":"post-prerequisite image-selection failure","output_hash":"sha256:da900e253fe727b6be2a3b513503bd5eff8eafe375ad9c3f9eb1d79c4177a427"},{"command":"uv run env PATH=/nonexistent /home/aparra/Desarrollo/odoo-forge/.venv/bin/python -m pytest -m integration tests/adapters/test_docker_provider_integration.py -q","exit_code":0,"output_hash":"sha256:26a8c0cebd8d31531e2d6d80d38d0a4d997471b06d11d56c62a1dcb615aaa478"},{"command":"uv run pytest","exit_code":0,"output_hash":"sha256:abadf38d98e01c5e72a64457c2b1039f0184fcf58a97ad40405e0b7cc0782766"},{"command":"ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q","exit_code":0,"output_hash":"sha256:ee769c0dc4dddf9f0dc472891ab0bcff30344cd9d653aa3f10186412a9177046"},{"command":"./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19","exit_code":0,"output_hash":"sha256:9bb04d8f814e2d473ea53ef32b8378051516556d0b6aa6c6b4b5093c62f2ba49"},{"command":"uv run pytest tests/adapters/test_docker_provider.py -q --cov=odoo_forge_docker.provider --cov-branch --cov-report=term-missing","exit_code":0,"output_hash":"sha256:5e86eb9877c767172ec437dc4f92c3b402a70e7339efa6064e5302063d1e63dd"},{"command":"uv run ruff check","exit_code":0,"output_hash":"sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18"},{"command":"uv run ruff format --check","exit_code":0,"output_hash":"sha256:1a9301f4cf03fa0d5c4d8f77f50252de3a09f3dbe30fd813f1131981eceb1770"},{"command":"uv run mypy","exit_code":0,"output_hash":"sha256:a7c4aae49ff9d21cbf4edf1b955366f4cb545b2dbf41b63329a9f1c16b3b0c5d"},{"command":"uv run lint-imports","exit_code":0,"output_hash":"sha256:2ec1151949b927abca48266b58cbd6caa54de49983e2f193d09d1b7230643333"},{"command":"git diff --check","exit_code":0,"output_hash":"sha256:01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"},{"command":"independent Docker residual queries for integration and smoke prefixes","exit_code":0,"output_hash":"sha256:7bde5ffafe0bcdea9102e8b089b49f29a278ad8d8fc92ff9a6d6dd25cca982fe"},{"command":"gentle-ai review validate --gate post-apply --cwd /home/aparra/Desarrollo/odoo-forge --lineage review-a49dc58752713b78","exit_code":0,"output_hash":"sha256:22a53d67520d6f0d1d4154367970022952016f7fd09c82e9e9be0f05911ca59b"}],"requirements":{"complete":1,"total":1},"review":{"authority_revision":"sha256:808537a52e707154698ac8e9999d7279d5889ef3f152e30a6aa719e6f994e34d","candidate_tree":"aefce973f78cf8af7da01f65440b02540d315ff2","generation":1,"lineage":"review-a49dc58752713b78","paths_digest":"sha256:d2b2fbb7e0585622941dd7ccc0d811809e3f3797b1b0dc6ae6d75c360ff1cd0d"},"scenarios":{"complete":13,"total":13},"tasks":{"complete":19,"total":19},"verdict":"pass"}
```

### Verdict and Archive Safety

**PASS** — requirements 1/1, scenarios 13/13, tasks 19/19, blockers 0, critical findings 0.

**Archive safe**: **Yes**, subject to the archive gate revalidating this exact passing envelope and bound approved lineage. Verification wrote only this report and did not modify implementation, tests, other planning artifacts, Git index/history, branches, remotes, archive state, PRs, or review state.

### Result Contract

```yaml
status: success
executive_summary: Independent Strict-TDD verification passed all 1 requirement, 13 scenarios, 19 tasks, focused/default/real-Docker/factory runtime commands, static checks, build, review binding, and residual checks.
artifacts:
  - openspec/changes/stabilize-real-docker-baseline/verify-report.md
next_recommended: archive
risks: No blocking risk; the existing exact-name-plus-not-found cleanup classifier follow-up remains a non-blocking suggestion, and registry-side future tag mutation is outside local digest evidence.
skill_resolution: paths-injected
```
