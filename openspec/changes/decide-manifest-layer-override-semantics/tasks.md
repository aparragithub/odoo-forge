# Tasks: Decide Manifest Layer and Override Semantics

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 900–1,200 lines |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | auto-chain (interactive approval remains required) |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal / estimate | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | v2 lock models/reader (180–260 lines) | PR 1; base=tracker/integration | `uv run pytest tests/manifest/test_lockfile_format.py` | N/A: pure serialization tests are runtime evidence | lockfile models/reader and tests |
| 2 | Override validation/effective Git locking (220–320 lines) | PR 2; base=PR 1 branch | `uv run pytest tests/manifest/test_composition.py tests/manifest/test_locking.py` | N/A: injected fake provider tests are runtime evidence | validation/locking and tests |
| 3 | Published port, adapter, DI (220–320 lines) | PR 3; base=PR 2 branch | `uv run pytest tests/ports tests/adapters tests/manifest/test_locking.py` | N/A: fake registry/provider tests are runtime evidence | port, adapter, DI and tests |
| 4 | Projection/drift/CLI safety/compatibility (260–360 lines) | PR 4; base=PR 3 branch | `uv run pytest tests/manifest tests/cli` | N/A: automated CLI tests are the runtime evidence; no tracked fixture writes | consumers/CLI safety and tests |

Only tracker/integration merges to main; no size exception. Child diffs exclude prior slices.

## Phase 1: RED — Contracts and lock foundation

- [x] 1.1 RED: Add failing `tests/manifest/test_lockfile_format.py` cases for version, key order, v2 round-trip, versionless v1, and unknown-version rejection.
- [x] 1.2 GREEN: Modify `src/odoo_forge/manifest/lockfile.py` with v2 models/dispatch (`git_layers`, `published_layers`, integer versions); REFACTOR canonical JSON and v1 normalization without fabricated published entries.
- [x] 1.3 RED: Add composition/locking failures for missing targets, duplicate/unknown URL, published/core targets, missing digest, and zero resolver calls; GREEN/REFACTOR `composition.py` validation and effective Git locking.

## Phase 2: RED — Published resolution and dependency injection

- [ ] 2.1 RED: Add `tests/ports/` and `tests/adapters/` failures for immutable resolution and typed not-found/digest errors; GREEN/REFACTOR `src/odoo_forge/ports/published_artifact_resolver.py`, `src/odoo_forge/manifest/artifacts.py`, and registry adapter.
- [ ] 2.2 RED: Extend locking tests for the combined published-version/digest plus overridden fork/ref/commit scenario; GREEN/REFACTOR `locking.py` and `src/odoo_forge_cli/main.py` resolver injection.

## Phase 3: RED — Consumers and CLI safety

- [ ] 3.1 RED: Add projection/drift failures proving published entries remain locked but are neither checked out nor compared to Git; GREEN/REFACTOR `projection.py` and `drift.py`.
- [ ] 3.2 RED: Add CLI failures for full pinned lock/readback, unresolved core ref, clean resolution error, and byte-identical atomic-write rollback; GREEN/REFACTOR `main.py` boundaries and compatibility paths.

## Phase 4: Verification and refactor

- [ ] 4.1 RED/GREEN: Add the odoo-idp composition fire fixture and verify all 12 spec scenarios (including published/override pinning and every lockfile case); REFACTOR shared fixtures and names.
- [ ] 4.2 Run `uv run pytest`, `uv run lint-imports`, `uv run mypy`, and `uv run ruff check`; fix only findings within the four work-unit boundaries.
