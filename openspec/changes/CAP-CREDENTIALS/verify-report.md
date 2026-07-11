```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:ad9f5cf71607593b58fb9a7dae101c4304a854b8e730f8a272681d4a584b8997
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 6/6
scenarios: 11/11
test_command: uv run pytest tests/adapters/test_docker_provider.py tests/credentials/test_materialization.py tests/cli/test_backend.py tests/backend/test_plan.py docs/tools/platform_portfolio/test_validate.py -q --cov=odoo_forge --cov=odoo_forge_docker --cov=odoo_forge_cli --cov-report=term-missing --cov-report=json:/tmp/opencode/cap_credentials_coverage.json
test_exit_code: 0
test_output_hash: sha256:27156928ff93557ba723a8104aef226197fc869082c596225257f1ef24df3ea9
build_command: uv run mypy src tests
build_exit_code: 0
build_output_hash: sha256:9ad320a85ca21c0eff33d60d04b500d1f61878a0511449d431cc57cbc0d0a44d
```

## Verification Report

**Change**: `CAP-CREDENTIALS`  
**Version**: N/A  
**Mode**: Strict TDD  
**Action context**: verify rerun after stale-artifact remediation validation  
**Apply-progress source**: Engram topic `sdd/CAP-CREDENTIALS/apply-progress`  
**Readiness state**: `AC-CAP-CREDENTIALS-READY` remains **proposed** with gap `G0`; no explicit repository acceptance approval was found.

### Completeness

| Metric | Value |
|---|---:|
| Requirements total | 6 |
| Requirements fully compliant | 6 |
| Scenarios total | 11 |
| Scenarios compliant | 11 |
| Tasks total | 6 |
| Tasks complete | 6 |
| Tasks incomplete | 0 |

All tasks in `openspec/changes/CAP-CREDENTIALS/tasks.md` are checked complete. Verification confirms the current repo implements the Docker transport as **read-only secret-file mounts at `/run/secrets/<key>` plus `<key>_FILE` pointers**, not as a live env-file handoff.

### Build & Tests Execution

| Check | Exact command | Exit | Output hash | Result |
|---|---|---:|---|---|
| Focused verification tests | `uv run pytest tests/adapters/test_docker_provider.py tests/credentials/test_materialization.py tests/cli/test_backend.py tests/backend/test_plan.py docs/tools/platform_portfolio/test_validate.py -q --cov=odoo_forge --cov=odoo_forge_docker --cov=odoo_forge_cli --cov-report=term-missing --cov-report=json:/tmp/opencode/cap_credentials_coverage.json` | 0 | `sha256:27156928ff93557ba723a8104aef226197fc869082c596225257f1ef24df3ea9` | `119 passed` |
| Portfolio runtime validator | `uv run python docs/tools/platform_portfolio/validate.py --root .` | 0 | `sha256:1e4cd8315547c9894a585f9535454e5eb7f5feb5cff8d76275e7ce6df740d8c3` | `VALIDATOR: CLEAN — 0 violations` |
| Changed-file linter | `uv run ruff check src/odoo_forge/backend/plan.py src/odoo_forge/credentials/types.py src/odoo_forge/credentials/materialization.py src/odoo_forge/credentials/errors.py src/odoo_forge_docker/credential_injection.py src/odoo_forge_docker/provider.py src/odoo_forge_cli/main.py tests/adapters/test_docker_provider.py tests/credentials/test_materialization.py tests/cli/test_backend.py tests/backend/test_plan.py docs/tools/platform_portfolio/test_validate.py docs/tools/platform_portfolio/validate.py` | 0 | `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | `All checks passed!` |
| Type checker | `uv run mypy src tests` | 0 | `sha256:9ad320a85ca21c0eff33d60d04b500d1f61878a0511449d431cc57cbc0d0a44d` | `Success: no issues found in 85 source files` |

### Spec Compliance Matrix

| # | Requirement | Scenario | Runtime evidence | Result |
|---:|---|---|---|---|
| 1 | First Store Decision Gate | Approved first store is recorded | `docs/tools/platform_portfolio/test_validate.py::TestValidator::test_credential_capability_records_sops_decision_and_readiness_pointers`; validator clean run | ✅ COMPLIANT |
| 2 | First Store Decision Gate | Store decision is missing | `docs/tools/platform_portfolio/test_validate.py::TestValidator::test_credential_readiness_blocks_a_missing_first_store_decision` | ✅ COMPLIANT |
| 3 | Handle-Only Consumer Boundary | Consumer receives an opaque handoff | `tests/cli/test_backend.py::test_run_binds_opaque_credentials_at_the_composition_root`; `tests/backend/test_plan.py::test_backend_plan_keeps_credential_handles_out_of_public_environment` | ✅ COMPLIANT |
| 4 | Handle-Only Consumer Boundary | Plaintext-bearing consumer shape is rejected | `tests/credentials/test_materialization.py::test_injection_values_reject_plaintext_bearing_fields`; `tests/backend/test_plan.py::test_backend_plan_never_places_passwords_in_public_environment` | ✅ COMPLIANT |
| 5 | Materialization Boundary and Plaintext Lifetime | Resolution completes without persistence | `tests/credentials/test_materialization.py::test_sops_materialization_returns_only_an_opaque_reference[database-42-database-42]`; `tests/credentials/test_materialization.py::test_sops_materialization_returns_only_an_opaque_reference[database-99-database-99]`; `tests/adapters/test_docker_provider.py::test_provider_uses_secret_files_and_removes_secrets_from_subprocess_observables` | ✅ COMPLIANT |
| 6 | Materialization Boundary and Plaintext Lifetime | Failed operation clears temporary plaintext | `tests/adapters/test_docker_provider.py::test_sops_env_file_injector_cleans_up_when_docker_launch_fails`; `tests/adapters/test_docker_provider.py::test_provider_fails_closed_before_docker_when_sops_resolution_is_unavailable` | ✅ COMPLIANT |
| 7 | Redacted Failures and Diagnostics | Failure is reported with redaction | `tests/credentials/test_materialization.py::test_credential_errors_expose_only_redacted_public_detail[CredentialUnavailableError-credential material is unavailable]`; `tests/credentials/test_materialization.py::test_credential_errors_expose_only_redacted_public_detail[CredentialTargetRejectedError-credential target does not accept an opaque reference]`; `tests/adapters/test_docker_provider.py::test_provider_redacts_sops_resolver_diagnostics_before_docker_launch` | ✅ COMPLIANT |
| 8 | Target-Side Injection Handoff | Ref-only target handoff succeeds | `tests/adapters/test_docker_provider.py::test_run_container_argv_uses_secret_files_not_container_environment`; `tests/adapters/test_docker_provider.py::test_provider_uses_secret_files_and_removes_secrets_from_subprocess_observables`; `tests/cli/test_backend.py::test_default_backend_composition_configures_a_sops_resolver` | ✅ COMPLIANT |
| 9 | Target-Side Injection Handoff | Non-ref-capable target fails closed | `tests/credentials/test_materialization.py::test_non_ref_capable_target_fails_closed_without_exposing_diagnostic`; `tests/adapters/test_docker_provider.py::test_provider_fails_closed_before_docker_when_sops_resolution_is_unavailable` | ✅ COMPLIANT |
| 10 | Acceptance Evidence for Credential Readiness | Complete evidence advances readiness | `docs/tools/platform_portfolio/test_validate.py::TestValidator::test_credential_readiness_requires_explicit_approval_after_complete_evidence` | ✅ COMPLIANT |
| 11 | Acceptance Evidence for Credential Readiness | Incomplete evidence blocks downstream use | `docs/tools/platform_portfolio/test_validate.py::TestValidator::test_credential_readiness_pointers_are_catalogued_and_keep_the_gate_blocked`; validator clean run | ✅ COMPLIANT |

**Compliance summary**: 11/11 scenarios compliant.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| First Store Decision Gate | ✅ Implemented | `docs/specs/platform/portfolio.json` records `DPROV-SECRETS` as `decided`, `chosen = SOPS`, with evidence `S20,S43`. |
| Handle-Only Consumer Boundary | ✅ Implemented | `BackendCredentialBindings`, `CredentialHandle`, planner `secret_env`, and CLI composition keep consumer-visible state opaque. |
| Materialization Boundary and Plaintext Lifetime | ✅ Implemented | `SopsEnvFileInjector.secret_files()` writes `0600` files per secret and removes them after use; provider never injects plaintext into Docker argv or subprocess env. |
| Redacted Failures and Diagnostics | ✅ Implemented | Credential errors collapse to public details only; provider diagnostics redact resolved values before surfacing them. |
| Target-Side Injection Handoff | ✅ Implemented | Docker launch uses bind mounts to `/run/secrets/<key>` and only exposes `<key>_FILE=/run/secrets/<key>` pointers. |
| Acceptance Evidence for Credential Readiness | ✅ Implemented | Live repo evidence keeps `AC-CAP-CREDENTIALS-READY` at `status: proposed` with `gaps: ["G0"]`; only the in-memory test fixture proves the conditional approved/no-gap path. |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| Contract proof seam uses real CLI → planner → Docker path | ✅ Yes | `_make_backend_provider()` wires `SopsCommandResolver` into `DockerBackendProvider`; planner and provider keep handle transport opaque until final injection. |
| `CredentialHandle` ownership stays at composition root | ✅ Yes | `src/odoo_forge_cli/main.py` binds handles once; `src/odoo_forge/credentials/types.py` remains the opaque contract owner. |
| Safe launch transport uses secret-file mounts and `*_FILE` pointers | ✅ Yes | `_run_container_argv()` emits `--mount type=bind,...target=/run/secrets/<key>,readonly` plus `-e <key>_FILE=/run/secrets/<key>`. |
| Readiness evidence remains documentary until explicit approval exists | ✅ Yes | Live portfolio state still keeps `AC-CAP-CREDENTIALS-READY` proposed and gap-blocked; verification found no repository artifact that advances it. |

### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | Engram topic `sdd/CAP-CREDENTIALS/apply-progress` includes a TDD Cycle Evidence table with 5 rows. |
| All tasks have tests | ✅ | 5/5 TDD rows map to current existing test files. |
| RED confirmed (tests exist) | ✅ | All reported test files exist in the current repo. |
| GREEN confirmed (tests pass) | ✅ | Fresh strict rerun passed all 119 collected tests. |
| Triangulation adequate | ✅ | The suite covers success, rejection, redaction, blocked-readiness, and conditional-approval branches with distinct cases. |
| Safety Net for modified files | ✅ | The documented safety-net claims remain plausible against the current changed files and rerun. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 26 | 2 | pytest |
| Integration | 93 | 3 | pytest, Typer runner, unittest under pytest |
| E2E | 0 | 0 | not installed / not used |
| **Total** | **119** | **5** | |

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|---|---:|---:|---|---|
| `src/odoo_forge/backend/plan.py` | 100% | 100% | — | ✅ Excellent |
| `src/odoo_forge/credentials/errors.py` | 100% | — | — | ✅ Excellent |
| `src/odoo_forge/credentials/materialization.py` | 100% | 100% | — | ✅ Excellent |
| `src/odoo_forge/credentials/types.py` | 100% | — | — | ✅ Excellent |
| `src/odoo_forge_cli/main.py` | 45% | 18% | `60,65,75,98-111,124-134,139-153,159-165,173-179,187-193,201-207,217-257,267-296,311-344,356-383,409-413,477-481,601->603` | ⚠️ Low |
| `src/odoo_forge_docker/credential_injection.py` | 81% | 62% | `26-40,88,102` | ⚠️ Acceptable |
| `src/odoo_forge_docker/provider.py` | 96% | 94% | `239-240,295,333,343-344,371,374` | ✅ Excellent |

**Average changed file coverage**: 88.8% line coverage.

### Assertion Quality

No tautologies, empty ghost-loop assertions, smoke-test-only cases, or plaintext-free-but-behaviorless checks were found in the focused CAP-CREDENTIALS verification files.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics

**Linter**: ✅ No errors or warnings in changed source/test/doc paths.  
**Type Checker**: ✅ No errors.  
**Coverage**: ⚠️ Strong on planner/materialization/provider surfaces, but `src/odoo_forge_cli/main.py` remains low at 45% line / 18% branch coverage.  
**Runtime validator**: ✅ Clean, and it preserves blocked readiness.  
**Build**: ➖ No packaging build was needed for this slice; `mypy` remained the available build-equivalent gate.

### Issues Found

#### CRITICAL

None.

#### WARNING

1. `src/odoo_forge_cli/main.py` is part of the verified surface but only reached 45% line coverage and 18% branch coverage in the focused strict rerun.
2. The Engram `sdd/CAP-CREDENTIALS/apply-progress` artifact still uses historical `env-file` wording for tasks 1.1/1.2, while the current runtime transport is secret-file mounts plus `*_FILE` pointers. Verification used the live code and current tests, not that stale wording.
3. The focused pytest coverage run still emits the non-fatal `module-not-measured` warning because coverage starts after some imports.

#### SUGGESTION

None.

### Verdict

**PASS WITH WARNINGS**

The current repo satisfies all 6 requirements and all 11 scenarios under a fresh strict rerun, but readiness still must remain **proposed/blocked** because the live portfolio record has no explicit acceptance approval and still carries gap `G0`.
