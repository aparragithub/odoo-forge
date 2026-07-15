# Apply Progress: Decide Manifest Layer and Override Semantics

## Completed Tasks
- [x] 1.1 RED: lockfile-format contracts
- [x] 1.2 GREEN/REFACTOR: v1/v2 lockfile models and dispatch

## TDD Cycle Evidence
| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/manifest/test_lockfile_format.py` | Unit | `uv run pytest tests/manifest/test_lockfile_format.py`: 4 passed | Added v2 imports/contracts; exact RED: collection ImportError for missing `ResolvedGitLayer` | Completed with 1.2: 8 passed | v2 Git+published fixture; unknown versions `0`, `3` | Test cases remain focused |
| 1.2 | `tests/manifest/test_lockfile_format.py` | Unit | Same 4 passed baseline | Used 1.1's failing contracts before production edits | `uv run pytest tests/manifest/test_lockfile_format.py`: 8 passed | v1/v2 dispatch plus two unsupported versions | Extracted explicit v1/v2 input models and compatibility view; 8 passed |

## Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/manifest/test_lockfile_format.py` — exit 0, 8 passed |
| Narrow dependent tests | `uv run pytest tests/manifest/test_locking.py tests/manifest/test_drift.py tests/manifest/test_projection.py` — exit 0, 40 passed |
| Runtime harness | N/A — pure serialization unit; focused pytest exercises every runtime path. |
| Static checks | `uv run ruff check src/odoo_forge/manifest/lockfile.py tests/manifest/test_lockfile_format.py` and `uv run mypy src/odoo_forge/manifest/lockfile.py tests/manifest/test_lockfile_format.py` — exit 0. |
| Rollback boundary | Revert `lockfile.py` v2 models/dispatch and `test_lockfile_format.py`; no resolver, adapter, CLI, projection, or drift behavior is changed. |

## Delivery
- Chained PR slice 1, base: `feat/decide-manifest-layer-override-semantics`; no commit, push, or PR created.
- Authored implementation/test diff before SDD metadata: 204 additions, 18 deletions (222 lines).
## R3-001 / Scope Expansion Evidence
- Maintainer terminally escalated `review-6ef5bb0d56b34227`; it was not reopened or remediated.
| Stage | Evidence |
|---|---|
| RED | `uv run pytest tests/manifest/test_locking.py tests/cli/test_lock.py` — exit 1, 16 passed / 1 failed: CLI expected v1 but generated lock is v2. |
| GREEN | `uv run pytest tests/manifest/test_lockfile_format.py tests/manifest/test_locking.py tests/cli/test_lock.py` — exit 0, 26 passed. |
| REFACTOR | Updated only the CLI contract to assert the full v2 top-level canonical shape; no production change. |
| Rollback | Revert the v2 CLI expectation in `tests/cli/test_lock.py`; production remains untouched. |

## R3-002 / Type Compatibility Evidence
- Maintainer-authorized scope after `review-c643750810c8b736` failed to finalize; no old lineage was reopened.
| Stage | Evidence |
|---|---|
| RED | `uv run mypy` — exit 1, 13 `Lockfile(layers=...)` call-argument errors in 6 files. |
| GREEN | Typed `Lockfile` constructor overloads preserve the runtime `layers` alias; `uv run mypy` — exit 0, 105 files checked. |
| CLI translation | Existing `_load_lock` `ValueError` translation retained; `uv run pytest tests/cli/test_validate.py` — exit 0, 10 passed. |
| Regression | 59-test focused command — exit 0, 59 passed; targeted Ruff — exit 0. |
| Rollback | Revert `Lockfile` overloads; runtime field aliases and v1/v2 serialization remain otherwise unchanged. |
