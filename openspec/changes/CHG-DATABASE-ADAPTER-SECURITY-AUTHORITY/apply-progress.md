# Apply Progress: Docker Database Adapter Security Authority

## Slice 1 — Durable Store

Completed tasks: 1.1, 1.2. PR 1 targets the feature/tracker branch; no later slice was started.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/adapters/test_postgres_docker_authority.py` | Unit/filesystem | N/A (new files) | `uv run pytest tests/adapters/test_postgres_docker_authority.py -q` → collection failed: module absent | 8 passed after 1.2 | 8 custody/failure scenarios | None needed; green rerun passed |
| 1.2 | `tests/adapters/test_postgres_docker_authority.py` | Unit/filesystem | N/A (new file) | Same missing-module failure; permissive-state regression also failed before its fix | 8 passed | Private custody, symlink, state loss/corruption, lock, crash, generation paths | None needed; checks passed |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/adapters/test_postgres_docker_authority.py -q` → exit 0, 8 passed |
| Runtime harness | N/A: this slice has only a local filesystem custody boundary; Docker lifecycle is Slice 3+ |
| Static checks | `uv run ruff check src/odoo_forge_postgres_docker/authority.py tests/adapters/test_postgres_docker_authority.py` → exit 0; `uv run mypy src/odoo_forge_postgres_docker/authority.py tests/adapters/test_postgres_docker_authority.py` → exit 0 |
| Rollback boundary | Remove `authority.py` and `test_postgres_docker_authority.py`; no provider, routing, credentials, signing, or Docker behavior changed |

## Remaining

Tasks 3.1–5.3 remain pending, including provider, secret-injection, Docker, readiness, and final-lineage work.

## Slice 2 — Signing and Evidence

Completed tasks: 2.1, 2.2, 2.3. PR 2 targets PR 1 in the feature-branch chain; Slice 3 was not started.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 2.1 | `tests/adapters/test_postgres_docker_authority.py` | Unit/filesystem | 12 passed | `uv run pytest tests/adapters/test_postgres_docker_authority.py -q` → 3 failed, 12 passed (missing evidence APIs) | 15 passed | Tamper/key/schema; rotation/recovery; replay/expiry; imported evidence/redaction | Type-narrowed verifier; 15 passed |
| 2.2 | `tests/adapters/test_postgres_docker_authority.py` | Unit/filesystem | 12 passed | Same 3 missing-API failures before implementation | 15 passed after `cryptography` resolution and minimal keyring/evidence implementation | Three independent evidence paths | Clean after Ruff/mypy fixes; 15 passed |
| 2.3 | `tests/adapters/test_postgres_docker_authority.py` | Build/static verification | 15 passed | N/A: verification-only task; its required behaviors were RED in 2.1 | 15 passed; build and mypy green | N/A: no production branch | Final test/build/type-check rerun passed |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/adapters/test_postgres_docker_authority.py -q` → exit 0, 15 passed |
| Runtime harness | N/A: Slice 2 is a local keyring/evidence unit; Docker lifecycle/runtime observation is Slice 3+ |
| Build | `uv build` → exit 0; source distribution and wheel built |
| Static checks | `uv run ruff check src/odoo_forge_postgres_docker/authority.py tests/adapters/test_postgres_docker_authority.py` → exit 0; `uv run mypy` → exit 0, 112 source files |
| Rollback boundary | Revert `pyproject.toml`, `uv.lock`, and Slice 2 keyring/evidence additions in `authority.py` plus their authority tests; custody foundation and all provider/routing behavior remain untouched |

### Delivery Boundary

- Strategy: feature-branch-chain; PR 2 targets PR 1.
- Authored implementation delta: 388 additions, 0 deletions (dependency metadata, authority code, and authority tests; excludes existing Slice 1 baseline and generated build output).

## Bounded Correction Evidence — review-06b86f4d6b06a478

| Task | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|
| Frozen R2-001/R3-001/R4-001 | 4 failed, 8 passed | 12 passed | deleted/dangling state; short/zero writes | None needed |

| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/adapters/test_postgres_docker_authority.py -q` → exit 0, 12 passed |
| Runtime harness | N/A: local filesystem durability boundary |
| Rollback boundary | Revert only `authority.py` and its custody tests |

## Bounded Correction Evidence — review-bd4c52f5b2c4c903

| Frozen IDs | RED | GREEN |
|---|---|---|
| R1-001 | label-only reconcile test failed | authority-required reconcile/delete/cleanup: 41 provider tests passed |
| R2-001/R3-001 | 3 schema-valid record mutations accepted | `read()`/`recover()` reject signed-record tampering: 18 authority tests passed |

| Evidence | Result |
|---|---|
| Focused tests | `uv run pytest tests/adapters/test_postgres_docker_authority.py tests/adapters/test_postgres_docker_provider.py -q` → exit 0, 59 passed |
| Static checks | Ruff and mypy on changed authority/provider paths → exit 0 |
| Rollback boundary | Revert local-record signatures, authority injection, and focused tests only |

## Slice 3 — Budget Gate

Tasks 3.1 and 3.2 remain unchecked. The already-landed Slice 3 corrections consume 348 authored lines (323 additions, 25 deletions). Completing durable reserve/bind/activate/retire transitions plus the outstanding unsupported-runtime coverage requires changing `authority.py`, `provider.py`, and provider tests beyond the 52 remaining lines, so this slice must be split before further implementation.

### TDD Cycle Evidence

| Task | Safety net | RED | GREEN | Refactor |
|---|---|---|---|---|
| 3.1/3.2 | `uv run pytest tests/adapters/test_postgres_docker_provider.py -q` → 43 passed | Reserve-before-Docker lifecycle test → 1 failed, 43 deselected (authority state absent) | Not run: implementation reverted at budget gate | N/A |

## Slice 3A — Existing Correction Boundary

Completed task: 3A.2. The approved correction-backed default authority, provision persistence, signed immutable Docker-ID verification, and label-only fail-closed rejection were preserved; no correction behavior was rewritten.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 3A.2 | `tests/adapters/test_postgres_docker_authority.py`, `tests/adapters/test_postgres_docker_provider.py` | Unit/mocked Docker | 61 passed | Existing correction RED evidence retained | `uv run pytest tests/adapters/test_postgres_docker_authority.py tests/adapters/test_postgres_docker_provider.py -q` → 67 passed | Authority absence, signed-ID mismatch, and label-only rejection retained | No correction refactor; focused rerun passed |

## Slice 3B — Remaining Lifecycle

Completed tasks: 3B.1, 3B.2, 3B.3. PR 3B targets PR 3A in the feature-branch chain; PR 4 was not started.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 3B.1 | `tests/adapters/test_postgres_docker_provider.py` | Unit/mocked Docker | 61 focused tests passed | `uv run pytest tests/adapters/test_postgres_docker_provider.py -q` → 6 failed, 43 passed (missing transitions, pre-Docker guard, ID validation, runtime failure typing) | 49 provider tests passed after minimal lifecycle wiring | Reserve before run; bind/activate; retire/lost authority; two injected IDs; unsupported runtime | Formatting/type-only cleanup; focused tests passed |
| 3B.2 | `tests/adapters/test_postgres_docker_provider.py` | Unit/mocked Docker | 61 focused tests passed | Same 6 failing RED cases | 67 authority/provider tests passed | Valid lifecycle and rejected authority/runtime/identifier paths | Transition helper extraction and formatting; 67 passed |
| 3B.3 | Focused authority/provider suites | Static/focused verification | 67 passed | N/A: verification-only; required RED cases are recorded in 3B.1 | 67 passed; Ruff and mypy exit 0 | N/A: no additional production branch | No refactor required after static checks |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/adapters/test_postgres_docker_authority.py tests/adapters/test_postgres_docker_provider.py -q` → exit 0, 67 passed |
| Runtime harness | N/A: PR 3B uses mocked Docker lifecycle boundaries; real Docker runtime proof is explicitly PR 5 |
| Static checks | `uv run ruff check src/odoo_forge_postgres_docker/authority.py src/odoo_forge_postgres_docker/provider.py tests/adapters/test_postgres_docker_authority.py tests/adapters/test_postgres_docker_provider.py` → exit 0; `uv run mypy` on the same four paths → exit 0, no issues |
| Rollback boundary | Revert only PR 3B transition APIs in `authority.py`, lifecycle wiring in `provider.py`, and the PR 3B provider lifecycle tests; retain the approved PR 3A authority/default/provision/immutable-ID behavior |

### Delivery Boundary

- Strategy: feature-branch-chain; PR 3B targets PR 3A, never `main`.
- Incremental PR 3B authored delta: 217 additions, 22 deletions (239 changed lines), including lifecycle tests and OpenSpec task/progress evidence; below the 400-line hard cap.
- Out of scope: PR 4 secret-file/`_FILE` injection, real-Docker runtime proof, reviews, commits, pushes, and PR creation.

## Slice 4 — Safe Credential Injection

Completed task: 4.1. PR 4 targets PR 3B in the feature-branch chain; PR 5 was not started.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 4.1 | `tests/adapters/test_postgres_docker_secret_injection.py`, `tests/adapters/test_postgres_docker_provider.py` | Unit/mocked Docker + filesystem | `uv run pytest tests/adapters/test_postgres_docker_provider.py -q` → 52 passed | Secret-injection test collection failed: `ModuleNotFoundError` | `uv run pytest tests/adapters/test_postgres_docker_secret_injection.py tests/adapters/test_postgres_docker_provider.py -q` → 53 passed | Private success, readiness failure erasure, and two rejected target/reference paths | Formatting/type fixes; focused suite remained green |

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/adapters/test_postgres_docker_secret_injection.py tests/adapters/test_postgres_docker_provider.py -q` → exit 0, 53 passed |
| Runtime harness | N/A: protected file and mocked Docker argv boundaries are the PR 4 scope; real Docker proof is explicitly PR 5 |
| Static checks | Ruff and mypy on the two production files and two focused test files → exit 0 |
| Rollback boundary | Revert `secret_injection.py`, its tests, and the provider's `_FILE`/bind-mount wiring; retain authority lifecycle and opaque materialization contracts |

### Delivery Boundary

- Strategy: feature-branch-chain; PR 4 targets PR 3B, never `main`.
- Out of scope: real-Docker/readiness/final-lineage proof (PR 5), reviews, commits, pushes, and PR creation.

## Slice 5 — Integration and Final Proof

Completed tasks: 5.1, 5.2. Executed from the final chain lineage on `main` at `8233899`
against a real Docker Engine (29.6.1) and the official `postgres:16` image.

### Real-Docker Acceptance Evidence

| Property | Test | Result |
|---|---|---|
| Password enforcement (injected secret is the only accepted password) | `test_provision_enforces_only_the_injected_secret_as_the_password` | Peer container over the bridge: correct password connects, `wrong-*` is rejected by `scram-sha-256`; loopback `trust` is deliberately not used as the proof path |
| Secret absence from `Config.Env` | `test_provisioned_container_never_exposes_the_plaintext_secret_in_config_env` | `Config.Env` carries only `POSTGRES_PASSWORD_FILE=…`; no `POSTGRES_PASSWORD=` and no plaintext substring |
| Restart-durable authority (daemon-restart reconcile/cleanup) | `test_daemon_restart_reconcile_and_cleanup_survive_on_durable_authority` | A fresh provider on the persisted signed records reconciles and cleans a stopped container; the erased secret mount means containers are reconciled/cleaned, never re-run |
| Foreign survival + reconcile + cleanup | `test_provision_reconcile_foreign_survival_and_cleanup_against_real_docker` | Owned lifecycle cannot remove an independently created container |
| Live-ready signed attestation | `test_runtime_attestation_requires_a_live_ready_docker_container` | `RuntimeOwnershipEvidence` minted only after live ownership + readiness; identifier absent from repr |
| Forced-readiness rollback | `test_forced_readiness_failure_rolls_back_the_real_created_container` | Real created container rolled back; secret redacted from the error |
| Opaque restore handoff + cleanup | `test_restore_uses_an_opaque_artifact_handoff_and_real_cleanup` | Opaque component injected over loopback trust; content restored; real cleanup leaves no residual |
| Redacted credential/restore failures | `test_credential_and_restore_failures_are_redacted_before_docker_mutation` | Secrets never surface in typed errors |

Forged/stale/missing/replay signed-evidence rejection is proved at the unit layer
(`test_signed_evidence_rejects_tampering_unknown_keys_and_invalid_schema`,
`test_rejects_schema_valid_tampering_of_signed_ownership_records`,
`test_rotation_recovery_and_replay_or_expired_nonce_are_rejected`,
`test_imported_or_inspect_minted_evidence_is_rejected_and_errors_are_redacted`).

### Work Unit Evidence

| Evidence | Result |
|---|---|
| Real-Docker suite | `uv run pytest tests/adapters/test_postgres_docker_provider_integration.py -m real_docker` → 8 passed (Docker 29.6.1, `postgres:16`) |
| Unit + contract suite | `uv run pytest` → 662 passed, 14 deselected |
| Static checks | `ruff check .`, `ruff format --check .`, `uv run mypy` (119 files), `lint-imports` (6/6 contracts) → all clean |
| Build | `uv build --offline` → source + wheel built |
| Final-lineage evidence | Regenerated from the `main`@`8233899` chain lineage; predecessor review evidence not read or reused |

### Delivery Boundary

- Strategy: feature-branch-chain; Slice 5 targets `main` at `8233899` via its own PR.
- Design note: erasing the host secret after provisioning makes containers non-restartable by
  design; durability is provided by the persisted signed ownership authority, not by the container.
