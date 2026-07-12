# Apply Progress: CAP-DATA-ARTIFACTS

## Status

All implementation tasks are complete. The contract remains prerequisite-only: no storage adapter, restore orchestration, anonymization, or control-plane behavior was added.

## Completed Tasks

- [x] 1. **RED — Contract tests for the prerequisite surface**
  - Added `tests/data_artifacts/test_contracts.py` for opaque references, frozen restore manifests, required database+filestore membership, typed fail-closed readiness/discard shapes, redacted extra-field rejection, and the capability protocol.
- [x] 2. **GREEN — Implement the pure-core data-artifact contract**
  - Added frozen contract types, coherent restore-set validation, typed outcomes, and `DataArtifactCapability` in `src/odoo_forge/data_artifacts/contracts.py`.
  - Kept `DataArtifactRef` string-backed and opaque; re-exported only the stable capability surface.
- [x] 3. **TRIANGULATE — Lock downstream compatibility at the restore port**
  - Added explicit restore-port tests that pin one `DataArtifactRef` input and forbid separate database/filestore parameters.
  - Clarified the existing port docstring; the `restore` signature is unchanged.
- [x] 4. **REFACTOR — Final strict-TDD sweep**
  - Removed duplicated restore signature coverage from the generic lifecycle loop while retaining an explicit implementation-signature assertion in the focused restore test.
  - Ran the complete suite successfully.

## Files Changed

- `tests/data_artifacts/test_contracts.py`
- `src/odoo_forge/data_artifacts/types.py`
- `src/odoo_forge/data_artifacts/contracts.py`
- `src/odoo_forge/data_artifacts/__init__.py`
- `tests/ports/test_database_provider.py`
- `src/odoo_forge/ports/database_provider.py`
- `openspec/changes/CAP-DATA-ARTIFACTS/tasks.md`
- `openspec/changes/CAP-DATA-ARTIFACTS/apply-progress.md`

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1–2 | `tests/data_artifacts/test_contracts.py` | Unit | `tests/database/test_types.py`: 8 passed | Import of missing public contract symbols failed during collection (exit 2) | 2 contract tests passed | Added duplicate-membership, typed fail-closed outcome, redacted-extra, and runtime-protocol cases; 5 passed | No cleanup needed; focused suite remained green |
| 3 | `tests/ports/test_database_provider.py` | Unit | 17 passed: `tests/ports/test_database_provider.py tests/database/test_types.py` | New restore documentation test failed: missing `opaque DataArtifactRef` (1 failed, 9 passed) | Clarified only the existing port docstring; 10 passed | Added distinct exact-input/signature test including separate-component rejection; 19 passed | Reformatted the docstring; 19 passed and Ruff passed |
| 4 | `tests/ports/test_database_provider.py` | Unit | 19 focused tests passed before cleanup | Approval-test refactor: no production behavior change required | N/A — no production behavior added | N/A — behavior already covered by explicit opaque-input and implementation-signature assertions | Removed duplicate generic restore-loop coverage; focused suite stayed at 19 passed, then full suite passed |

## Verification Evidence

- `uv run pytest tests/database/test_types.py -q` — 8 passed (baseline and post-change).
- `uv run pytest tests/data_artifacts/test_contracts.py -q` — RED: failed during collection because `ArtifactComponentKind` was not exported (exit 2).
- `uv run pytest tests/data_artifacts/test_contracts.py -q` — GREEN: 2 passed.
- `uv run pytest tests/data_artifacts/test_contracts.py -q && uv run pytest tests/database/test_types.py -q` — 5 passed; 8 passed.
- `uv run pytest tests/data_artifacts/test_contracts.py tests/database/test_types.py -q` — 13 passed.
- `uv run pytest tests/ports/test_database_provider.py tests/database/test_types.py -q` — task-3 safety net: 17 passed; final focused verification: 19 passed.
- `uv run pytest tests/ports/test_database_provider.py -q` — RED: 1 failed, 9 passed; GREEN: 10 passed.
- `uv run pytest` — 381 passed, 1 deselected.
- `uv run ruff check src/odoo_forge/data_artifacts tests/data_artifacts` — passed.
- `uv run ruff check src/odoo_forge/ports/database_provider.py tests/ports/test_database_provider.py` — passed.
- `git diff --check` — passed.

Runtime harness: N/A — this is a pure-domain contract and protocol documentation change with no adapter/runtime boundary.

Rollback boundary: revert the restore-port compatibility test/docstring adjustment independently; the pure-core contract remains separately removable by reverting `contracts.py`, its exports/type helper, and the data-artifact contract tests.

## Deviations

None. The task-4 cleanup was limited to duplicate test coverage; no public behavior changed.

## Remaining Tasks

None. All persisted implementation task checkboxes are marked `- [x]`.

## Workload / PR Boundary

Delivery strategy: `auto-chain`; chain strategy: `feature-branch-chain`.

Assigned work-unit boundary: downstream restore-port compatibility and final strict-TDD cleanup (tasks 3–4). It depends on the completed pure-core contract slice (tasks 1–2). No commit or PR was created.

```text
feature tracker
  └─ PR 1: pure-core contract (tasks 1–2)
       └─ PR 2: restore-port compatibility (task 3)
            └─ PR 3: final strict-TDD sweep (task 4) 📍
```

## Post-Implementation Review Correction

- [x] 5. **Review correction — strengthen contract invariants**
  - Added RED tests for missing restore identity/format/digest evidence, connection or secret-bearing opaque/redacted values, and contradictory discard residual states.
  - Required non-empty opaque restore and lineage identifiers, non-empty safe format markers, and supported hexadecimal `sha256`/`sha512` digests.
  - Rejected connection/secret-bearing values in opaque component and residual identifiers plus redacted detail; preserved the single string-backed `DataArtifactRef` contract.
  - Enforced that `COMPLETED` has no residual IDs and `RESIDUAL_FAILURE` has at least one.

### Review-correction TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 5 | `tests/data_artifacts/test_contracts.py` | Unit | 5 passed | 3 new tests failed as expected: missing integrity evidence, secret/URL fields, and contradictory discard states | 8 passed after minimal validators | Added invalid non-hex digest and URL residual cases; 8 passed | Extracted shared safety validators, formatted imports; focused tests and Ruff passed |

### Review-correction Verification Evidence

- `uv run pytest tests/data_artifacts/test_contracts.py -q` — safety net: 5 passed.
- `uv run pytest tests/data_artifacts/test_contracts.py -q` — RED: 3 failed, 5 passed.
- `uv run pytest tests/data_artifacts/test_contracts.py -q` — GREEN and triangulation/refactor: 8 passed.
- `uv run ruff check src/odoo_forge/data_artifacts/contracts.py tests/data_artifacts/test_contracts.py` — passed.
- `git diff --check` — passed.

Runtime harness: N/A — validators are pure-domain contract behavior with no adapter/runtime boundary.

Rollback boundary: revert the task-5 validators in `contracts.py` and their focused assertions in `test_contracts.py`; no downstream restore-port signature or artifact transport behavior changes.

## Structured Status Consumed

- `changeName`: `CAP-DATA-ARTIFACTS`
- `artifactStore`: `openspec`
- `applyState`: `ready`
- `nextRecommended`: `apply`
- `actionContext`: `repo-local`; workspace root `/home/aparra/Desarrollo/odoo-forge`; allowed edit root includes the workspace.
- Action-context warnings: none.

## Structured Status Produced

- `changeName`: `CAP-DATA-ARTIFACTS`
- `artifactStore`: `openspec`
- `applyState`: `all_done` (tasks 1–5 are visibly checked)
- `nextRecommended`: `verify`
- `actionContext`: `repo-local`; all changes remain under `/home/aparra/Desarrollo/odoo-forge`.
- Action-context warnings: none.
