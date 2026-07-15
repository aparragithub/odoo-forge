# Apply Progress: Decide Manifest Layer and Override Semantics

## Completed Tasks
- [x] 1.1 RED: lockfile-format contracts
- [x] 1.2 GREEN/REFACTOR: v1/v2 lockfile models and dispatch
- [x] 1.3 RED/GREEN/REFACTOR: exact override validation and effective Git locking
- [x] 2.1 RED/GREEN/REFACTOR: published resolver port, frozen value, typed failures, and registry adapter
- [x] 2.2 RED/GREEN/REFACTOR: injected artifact resolver, published lock entries, and CLI composition

## TDD Cycle Evidence
| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/manifest/test_lockfile_format.py` | Unit | `uv run pytest tests/manifest/test_lockfile_format.py`: 4 passed | Added v2 imports/contracts; exact RED: collection ImportError for missing `ResolvedGitLayer` | Completed with 1.2: 8 passed | v2 Git+published fixture; unknown versions `0`, `3` | Test cases remain focused |
| 1.2 | `tests/manifest/test_lockfile_format.py` | Unit | Same 4 passed baseline | Used 1.1's failing contracts before production edits | `uv run pytest tests/manifest/test_lockfile_format.py`: 8 passed | v1/v2 dispatch plus two unsupported versions | Extracted explicit v1/v2 input models and compatibility view; 8 passed |
| 1.3 | `tests/manifest/test_composition.py`, `tests/manifest/test_locking.py` | Unit | `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py`: 22 passed | Exact URL acceptance/rejection, duplicate target, core target, and replacement-before-resolution tests added before production edits; exit 1, 4 failed / 24 passed | `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py`: exit 0, 28 passed | Exact vs basename, three structurally invalid provider-free paths, and effective fork/ref/commit paths | Removed basename matching; extracted effective repo resolution; 28 passed |
| 2.1 | `tests/ports/test_published_artifact_resolver.py`, `tests/adapters/test_published_artifact_resolver.py` | Unit | New files | Import RED: exit 2, missing `manifest.artifacts`; GREEN: exit 0, 4 passed | Happy immutable resolution; not-found, missing-digest, and generic registry failures | Extracted adapter-local single-method registry protocol; 4 passed |
| 2.2 | `tests/manifest/test_locking.py`, `tests/cli/test_lock.py` | Unit | `uv run pytest tests/manifest/test_locking.py tests/cli/test_lock.py`: 53 passed | exit 1: missing CLI factory and `build_lock` third dependency | exit 0, 28 focused tests passed | Published digest plus overridden effective fork/ref/commit; CLI fake DI | Required explicit injected resolver; no service locator; all focused tests stay green |

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

## Work Unit 2 Evidence
| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py` — RED exit 1: 4 failed, 24 passed; GREEN/REFACTOR exit 0: 28 passed. |
| Narrow lockfile regression | `uv run pytest tests/manifest/test_lockfile_format.py` — exit 0, 9 passed. |
| Combined regression | `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py tests/manifest/test_lockfile_format.py` — exit 0, 37 passed. |
| Targeted quality | `uv run ruff check src/odoo_forge/manifest/composition.py src/odoo_forge/manifest/locking.py tests/manifest/test_composition.py tests/manifest/test_locking.py` — exit 0; `uv run mypy src/odoo_forge/manifest/composition.py src/odoo_forge/manifest/locking.py tests/manifest/test_composition.py tests/manifest/test_locking.py` — exit 0, no issues in 4 files. |
| Runtime harness | N/A — this is a pure-core boundary; injected fake `SourceProvider` proves that structurally invalid manifests invoke it zero times and that the effective fork/ref is resolved and persisted. |
| Rollback boundary | Revert only `composition.py`, `locking.py`, and their two manifest test files to restore declared Git URL/ref locking and prior basename validation; lockfile v1/v2 compatibility and all future resolver/adapter/CLI work remain untouched. |

## Delivery: Work Unit 2
- Mandatory feature-branch chain, PR #2 base: `feat/manifest-lock-v2` at `8c689ad`.
- Authored implementation/test diff against `8c689ad`: 177 additions + 39 deletions = 216 changed lines before SDD metadata; within the 220–320 forecast once task/progress evidence is included, and below the 400-line hard cap.
- No commit, push, PR, resolver/registry/DI, projection/drift, or new CLI wiring was created.

## Unit 2 Authorized Scope Expansion
- Maintainer authorized a new scope after CRITICAL review lineage `review-3d71d166a700e028`; that lineage was not reopened or remediated.
| Stage | Evidence |
|---|---|
| RED | Existing CLI fixture consumers failed with basename targets; after adding tracked-fixture and core-shadowing regressions, `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py tests/cli/test_lock.py tests/cli/test_validate.py` exited 1: 12 failed, 39 passed. |
| GREEN | Migrated `valid.project.yaml` and `odoo-idp.project.yaml` to exact URLs; rejected reserved `core` additional layers and explicit core overrides before resolution; updated the existing CLI lock assertion to effective fork/ref/commit. |
| REFACTOR | Removed the in-memory fixture rewrite and parameterized direct tracked-fixture composition coverage; no new abstraction was needed. |
| Focused tests | `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py` — exit 0, 31 passed. |
| CLI fixture consumers | `uv run pytest tests/cli/test_lock.py tests/cli/test_validate.py` — exit 0, 20 passed. |
| Unit 1 regression | `uv run pytest tests/manifest/test_lockfile_format.py` — exit 0, 9 passed. |
| Quality | `uv run ruff check src/odoo_forge/manifest/composition.py src/odoo_forge/manifest/locking.py tests/manifest/test_composition.py tests/manifest/test_locking.py tests/cli/test_lock.py` — exit 0; targeted mypy for the same Python paths — exit 0, no issues in 5 files. |
| Runtime harness | N/A — injected fake `SourceProvider` verifies the core-shadowing structure fails before any provider call; CLI tests exercise real Typer lock/validate paths with fixture files. |
| Rollback | Revert the two fixture URL migrations, reserved-name/core-override validation, and focused regression/CLI expectation changes together; no future-unit behavior is removed. |
- Current cumulative diff against `8c689ad`: 286 additions + 53 deletions = 339 changed lines, below the 400-line hard cap. |

## Work Unit 3 Evidence
| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/ports/test_published_artifact_resolver.py tests/adapters/test_published_artifact_resolver.py tests/manifest/test_locking.py tests/cli/test_lock.py` — exit 0, 28 passed. |
| Unit 1+2 regression | `uv run pytest tests/manifest/test_lockfile_format.py tests/manifest/test_composition.py tests/manifest/test_locking.py` — exit 0, 41 passed. |
| Quality | Targeted `uv run ruff check ...` — exit 0; `uv run lint-imports` — 6 contracts kept; `uv run mypy` — exit 0, 110 source files. |
| Runtime harness | N/A — registry interaction is fully exercised through the concrete adapter contract fake: fixture `registry://example/odoo-ee` maps to `ghcr.io/example/odoo-ee:19.0`, and digest/not-found/general failures are translated without network or Docker. |
| Rollback boundary | Revert only published-artifact port/value/adapter, resolver injection, and their focused tests; Unit 1/2 lockfile and Git override behavior remains intact. |

## Delivery: Work Unit 3
- Feature-branch-chain PR #3 base: `feat/manifest-git-overrides` / `bb1c229`; no commit, push, PR, review, projection, drift, or CLI safety work was created.
- Diff against `bb1c229` is within the 400-line hard cap, including OpenSpec metadata.

## Work Unit 4 Evidence
### TDD Cycle Evidence
| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 3.1 | `tests/manifest/test_projection.py`, `tests/manifest/test_drift.py` | Unit | `uv run pytest tests/manifest/test_projection.py tests/manifest/test_drift.py`: 31 passed | Added legacy-view guard tests first; exit 1, 2 failed / 31 passed because consumers used `lock.layers` | Changed consumers to `lock.git_layers`; exit 0, 33 passed | v2 published-only plus existing v1/Git projection and mismatch cases | Named the v2 Git-only iteration boundary; 33 passed |
| 3.2 | `tests/cli/test_lock.py` | CLI integration | `uv run pytest tests/cli/test_lock.py`: 10 passed | Pre-existing acceptance tests already cover full v2 readback, unresolved core ref, clean resolver error, and atomic rollback; no missing behavior was found | Verified unchanged: 10 passed | Existing success/failure and absent/existing-lock paths | No candidate refactor needed |
| 4.1 | `tests/manifest/test_composition.py`, `tests/manifest/test_lockfile_format.py`, `tests/manifest/test_locking.py`, `tests/cli/test_lock.py` | Unit/CLI integration | `uv run pytest tests/manifest tests/cli`: 175 passed | The tracked `odoo-idp.project.yaml` fire fixture and all scenario tests pre-existed this unit; no test-only mutation or duplicate test was added | 175 passed | Covers fixture composition, invalid targets, pinning, v1/v2, unknown versions, CLI lock/readback, core default, and failure rollback | No shared-fixture rename was needed |

### Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused test | `uv run pytest tests/manifest tests/cli` — exit 0, 175 passed. |
| Runtime harness | `uv run pytest tests/cli/test_lock.py` — exit 0, 10 passed through the real Typer `lock`/`validate` commands with temporary manifests and files; no shell/process boundary applies. |
| Rollback boundary | Revert only `projection.py`, `drift.py`, and their two focused test files to restore compatibility-view iteration; no lock model, resolver, adapter, or CLI behavior is removed. |

### Quality Gate
- `uv run lint-imports` — exit 0, 6 contracts kept.
- `uv run ruff check .` — exit 0, all checks passed.
- `uv run ruff format --check .` — exit 1: pre-existing formatting findings in unchanged `src/odoo_forge/manifest/composition.py`, `src/odoo_forge/manifest/locking.py`, and `tests/cli/test_lock.py`; not fixed because they are outside this Work Unit.
- `uv run mypy` — exit 0, no issues in 110 source files.
- `uv run pytest` — exit 0, 574 passed and 6 deselected.

## Delivery: Work Unit 4
- Feature-branch-chain PR #4 base: `feat/manifest-published-layers` / `ce2d165`; no commit, push, PR, review, or verify report was created.
- Diff against `ce2d165` before OpenSpec task/progress metadata: 87 additions + 5 deletions = 92 changed lines; below the 400-line hard cap.
- Task 4.2 remains unchecked: complete quality verification cannot be proven while the pre-existing formatter findings remain, and fixing them is explicitly out of scope.

## Work Unit 4 Quality Completion
- The formatter findings are owned by earlier units in this feature chain relative to tracker/main, so task 4.2 permits their mechanical correction.
- `uv run ruff format src/odoo_forge/manifest/composition.py src/odoo_forge/manifest/locking.py tests/cli/test_lock.py` reformatted exactly those three chain-owned files without behavioral changes.
- Exact CI order: `uv run lint-imports` — exit 0, 6 contracts kept; `uv run ruff check .` — exit 0; `uv run ruff format --check .` — exit 0, 113 files already formatted; `uv run mypy` — exit 0, no issues in 110 source files; `uv run pytest` — exit 0, 574 passed and 6 deselected.
- Task 4.2 is complete. Final task state: 9/9 checked.
- Final Unit 4 diff against `ce2d165`: 129 additions + 14 deletions = 143 changed lines, below the 400-line hard cap.
