# Tasks: CAP-CREDENTIALS

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 20-60 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR: factory secret-file contract proof |
| Delivery strategy | force-chained |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Baseline already accepted

- `src/odoo_forge_cli/main.py`, `src/odoo_forge/backend/plan.py`, and `src/odoo_forge/credentials/types.py` already carry opaque credential handles through the CLI/planner seam.
- `src/odoo_forge/credentials/errors.py`, `src/odoo_forge/credentials/materialization.py`, and `tests/credentials/test_materialization.py` already lock redacted failures, opaque descriptors, and fail-closed target rejection.
- `tests/backend/test_plan.py`, `tests/cli/test_backend.py`, `tests/ports/test_backend_provider.py`, and `tests/ports/test_database_provider.py` already pin the mixed baseline's opaque boundary behavior.
- `docs/specs/platform/portfolio.json` and `docs/tools/platform_portfolio/test_validate.py` already record `DPROV-SECRETS = SOPS` and keep `AC-CAP-CREDENTIALS-READY` proposed/blocked.

### Runtime seam delivered; readiness remains blocked

- `src/odoo_forge_docker/credential_injection.py` creates `0600` temporary secret files and removes them on all exit paths.
- `src/odoo_forge_docker/provider.py` consumes the injector, emits read-only secret-file mounts plus `*_FILE` pointers, and fails closed before Docker launch when no approved resolver is configured.
- Readiness remains blocked: the portfolio/readiness evidence in task 2.2 remains documentary rather than completion evidence.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Re-baseline the factory secret-file contract with a true RED-first shell harness. | PR 1 | `bash factory/tests/test-entrypoint-secret-files.sh` | `bash factory/tests/test-entrypoint-secret-files.sh` | `factory/entrypoint.sh`, `factory/wait-for-psql.py`, `factory/lib/credentials.sh`, `factory/tests/test-entrypoint-secret-files.sh` |

## Phase 1: Runtime seam

- [x] 1.1 Add `src/odoo_forge_docker/credential_injection.py` to resolve SOPS handles into 0600 temporary secret files and unlink them in `finally`.
- [x] 1.2 Update `src/odoo_forge_docker/provider.py` to consume the injector, use read-only secret-file mounts and `*_FILE` pointers, and avoid secret-bearing Docker configuration values.

## Phase 2: Verification and blocked readiness

- [x] 2.1 Extend `tests/adapters/test_docker_provider.py` with RED cases for secret-free argv/env/logs, secret-file cleanup on success/failure, and fail-closed rejection.
- [x] 2.2 Keep `docs/specs/platform/portfolio.json` and `docs/tools/platform_portfolio/test_validate.py` aligned so `AC-CAP-CREDENTIALS-READY` remains proposed and blocked.

## Phase 3: Blocking review remediation

- [x] 3.1 Configure the SOPS resolver at the CLI composition root and use target-native secret-file pointers so plaintext is absent from Docker container environment/configuration.
- [x] 3.2 Bind published Odoo ports to loopback, preserve redacted readiness diagnostics before rollback, and report cleanup residual resources.

## Phase 4: Protocol-integrity replacement

- [x] 4.1 Add the missing RED-first regression in `factory/tests/test-entrypoint-secret-files.sh` for `DB_PASSWORD_FILE` precedence and `wait-for-psql.py --help` (`--db_password_file` only), then make the smallest `factory/entrypoint.sh` / `factory/wait-for-psql.py` fix needed to pass.
- [x] 4.2 Resolve `credentials.sops.yaml` from the selected `--manifest` project directory rather than the process working directory.
- [x] 4.3 Add behavior-level tests for the SOPS subprocess CLI contract and manifest-scoped resolver construction.
- [x] 4.4 Make secret-file cleanup remove partial materialization residue without masking the original failure.
