# Tasks: Provider-Neutral Database Provider Port

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 420-560 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 values+errors → PR 2 protocol+conformance → PR 3 evidence wiring |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Add immutable database values and opaque cross-capability refs. | PR 1 | `uv run pytest tests/database/test_types.py -q` | N/A — pure-core value model, no runtime adapter boundary | `src/odoo_forge/database/*`, `src/odoo_forge/credentials/*`, `src/odoo_forge/data_artifacts/*`, matching tests |
| 2 | Add typed redacted failures plus runtime-checkable protocol and conformance checks. | PR 2 | `uv run pytest tests/database/test_errors.py tests/ports/test_database_provider.py -q` | N/A — contract/conformance only, no live provider execution | `src/odoo_forge/database/errors.py`, `src/odoo_forge/ports/database_provider.py`, related tests |
| 3 | Preserve verification evidence and keep import/type boundaries clean; portfolio attachment remains post-verify only. | PR 3 | `uv run pytest -q && uv run lint-imports && uv run mypy` | N/A — evidence-only change, no product runtime path | `docs/specs/platform/portfolio.json` evidence metadata only, after verification |

## Phase 1: Foundation / Value Model

- [x] 1.1 RED: Add `tests/database/test_types.py` for frozen/extra-forbidden values, `DatabaseCreation` composition, and rejection of secret-bearing fields/bytes.
- [x] 1.2 GREEN: Create `src/odoo_forge/database/types.py` with frozen `DatabaseSpec`, `DatabaseRef`, `DatabaseCreation`, `CreationReceipt`, `ResourceOwnership`, `CleanupReport`, and `OperationIdentity`.
- [x] 1.3 GREEN: Add opaque `CredentialHandle` and `DataArtifactRef` declarations in `src/odoo_forge/credentials/types.py` and `src/odoo_forge/data_artifacts/types.py`, plus package re-exports.
- [x] 1.4 REFACTOR: Add `src/odoo_forge/database/__init__.py` and tighten exports so provider values stay provider-owned and secret-free.

## Phase 2: Contract / Failures

- [x] 2.1 RED: Add `tests/database/test_errors.py` for typed invalid-request/unavailable/ownership/readiness failures and redacted cleanup residuals.
- [x] 2.2 GREEN: Implement `src/odoo_forge/database/errors.py` with sanitized error payloads and typed subclasses.
- [x] 2.3 RED: Add `tests/ports/test_database_provider.py` for exact six-method signatures, runtime-checkable protocol shape, and rejection of a bad fake provider.
- [x] 2.4 GREEN: Implement `src/odoo_forge/ports/database_provider.py` with the six-operation `Protocol` using type-only imports.

## Phase 3: Evidence / Verification

- [x] 3.1 VERIFY: Run `uv run pytest -q`, `uv run lint-imports`, and `uv run mypy` to confirm pure-core isolation and no adapter imports.
- [x] 3.2 VERIFY: Preserve the completed evidence bundle for runtime shape, exact signatures, immutable-value invariants, failure redaction, and safe cleanup.
- [x] 3.3 CLEANUP: Remove temporary helpers and confirm the change stays within provider-neutral X7 scope; keep Docker/runtime cutover out.

## Phase 4: Post-Verification Evidence Acceptance

- Post-verification archive gate: attach the approved proposal/spec/design plus verification receipt IDs to `docs/specs/platform/portfolio.json`, then advance `AC-PORT-DATABASE-PROVIDER-READY` only after verification is complete.
- This is a lifecycle action, not an apply task, and it is excluded from `sdd-verify` completion counting.
