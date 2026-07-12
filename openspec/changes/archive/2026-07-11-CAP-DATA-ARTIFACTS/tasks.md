## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~260–340 authored lines across the chain |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

# Tasks

- [x] 1. **RED — Contract tests for the prerequisite surface**
  - Add `tests/data_artifacts/test_contracts.py` to pin the opaque `DataArtifactRef` contract, frozen/redacted model rules, required database+filestore membership, fail-closed validation shapes, and the `DataArtifactCapability` protocol surface.
  - Keep the assertions focused on pure-domain shapes only; do not introduce adapter, workflow, anonymization, or control-plane concerns.
  - **Verify:** `uv run pytest tests/data_artifacts/test_contracts.py -q` should fail on the current codebase for the missing contract surface.
  - **Rollback:** remove the new contract test file.

- [x] 2. **GREEN — Implement the pure-core data-artifact contract**
  - Add `src/odoo_forge/data_artifacts/contracts.py` with the frozen manifest, component, readiness, discard, and protocol value types described by the spec.
  - Update `src/odoo_forge/data_artifacts/types.py` to keep `DataArtifactRef` opaque and host any shared frozen base model/helpers needed by the new contract types.
  - Update `src/odoo_forge/data_artifacts/__init__.py` to re-export only the stable public contract surface.
  - Enforce `extra="forbid"`, `hide_input_in_errors=True`, typed redacted failure codes, and the required database/filestore coherence membership rules.
  - **Verify:** the new contract tests pass, and `tests/database/test_types.py` still passes unchanged.
  - **Rollback:** remove `contracts.py` and revert the export/type updates.

- [x] 3. **TRIANGULATE — Lock downstream compatibility at the restore port**
  - Tighten `tests/ports/test_database_provider.py` so `DatabaseProvider.restore(...)` remains a single opaque `DataArtifactRef` input and nothing broader.
  - If a docstring clarification is needed, make it in `src/odoo_forge/ports/database_provider.py` without changing the signature.
  - **Verify:** `uv run pytest tests/ports/test_database_provider.py tests/database/test_types.py -q`.
  - **Rollback:** revert the compatibility test/docstring adjustment only; no adapter or orchestration changes.

- [x] 4. **REFACTOR — Final strict-TDD sweep**
  - Run the full suite with `uv run pytest` and remove any duplicated assertions or helper noise introduced during the contract work.
  - Keep the final diff inside the prerequisite capability boundary; do not expand into adapter implementation, orchestrator wiring, anonymization policy, or control-plane ownership.
  - **Verify:** full suite green with no new public behavior beyond the prerequisite contract surface.
  - **Rollback:** revert only the cleanup commit if it alters behavior.

- [x] 5. **Review correction — strengthen contract invariants**
  - Add RED contract tests for readiness integrity evidence, opaque/redacted no-secret boundaries, and contradictory discard states.
  - Enforce required identifiers, format markers, syntactically valid supported digests, redaction-safe opaque fields, and discard-code/residual consistency without changing the single opaque `DataArtifactRef` downstream input.
  - **Verify:** `uv run pytest tests/data_artifacts/test_contracts.py -q` and `uv run ruff check src/odoo_forge/data_artifacts/contracts.py tests/data_artifacts/test_contracts.py`.
  - **Rollback:** revert the contract validators and their focused tests only.
