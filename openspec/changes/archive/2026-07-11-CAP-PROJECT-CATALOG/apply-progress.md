# Apply Progress: CAP-PROJECT-CATALOG

## Status

PR 1 and PR 2 are complete: the pure project-catalog resolution contract, focused tests, and the portfolio readiness-evidence handoff are implemented. This supersedes the previous blocked-before-implementation record: the task tracker now contains completed Markdown checkboxes, and the authoritative native status reported `applyState: ready` with no blockers before this apply run.

## Structured status consumed

- `artifactStore`: `openspec`
- `applyState`: `ready`
- `nextRecommended`: `apply`
- `blockedReasons`: none
- `actionContext.mode`: `repo-local`
- `actionContext.workspaceRoot`: `/home/aparra/Desarrollo/odoo-forge-cap-parallel-sdd`
- `actionContext.allowedEditRoots`: `/home/aparra/Desarrollo/odoo-forge-cap-parallel-sdd`
- Warning: the initial progress record was blocked solely by missing Markdown checkboxes. That tracker defect was repaired before this retry; all edits remain inside the allowed workspace root.

## Completed tasks and persisted checkbox evidence

- [x] 1.1 **RED: lock the contract with focused tests first**
- [x] 1.2 **GREEN: implement the smallest pure-domain slice**
- [x] 1.3 **TRIANGULATE: prove the slice fits project standards**
- [x] 1.4 **REFACTOR: simplify without expanding scope**
- [x] 2.1 **Update readiness evidence for `AC-CAP-PROJECT-CATALOG-READY`**
- [x] 2.2 **Final bounded verification before archive**

`tasks.md` was reread after updating it and visibly contains each completion checkbox above.

## Implementation

- Added pure typed catalog models, the read-only `CatalogIndex` protocol, required-output validation, and `ProjectCatalogResolver`.
- Resolver normalizes identifiers, preserves exact match cardinality, and returns typed `catalog-not-found`, `ambiguous-resolution`, or `invalid-catalog` failures.
- Valid catalog records produce a fully materialized authority result with manifest reference, source context, data-policy default, and target default.
- No onboarding, provider execution, persistence, workspace materialization, tenancy, or control-plane behavior was added.
- Marked `CAP-PROJECT-CATALOG` and `AC-CAP-PROJECT-CATALOG-READY` achieved in `portfolio.json`, with evidence links to the normative spec, bounded design, resolver, and focused resolver tests.

## Files changed

- `tests/project_catalog/test_resolver.py`
- `src/odoo_forge/project_catalog/__init__.py`
- `src/odoo_forge/project_catalog/interfaces.py`
- `src/odoo_forge/project_catalog/models.py`
- `src/odoo_forge/project_catalog/validation.py`
- `src/odoo_forge/project_catalog/resolver.py`
- `openspec/changes/CAP-PROJECT-CATALOG/tasks.md`
- `openspec/changes/CAP-PROJECT-CATALOG/apply-progress.md`
- `docs/specs/platform/portfolio.json`

## Verification

- RED: `uv run pytest tests/project_catalog/test_resolver.py -q` failed during collection with `ModuleNotFoundError: No module named 'odoo_forge.project_catalog'`.
- GREEN: `uv run pytest tests/project_catalog/test_resolver.py -q` passed (1 test).
- `uv run pytest tests/project_catalog -q` passed (5 tests).
- `uv run mypy src/odoo_forge/project_catalog tests/project_catalog` passed.
- `uv run ruff check src/odoo_forge/project_catalog tests/project_catalog` passed.
- `uv run lint-imports` passed (6 contracts kept).
- `git diff --check` passed.
- PR 2 safety net and final verification: `uv run pytest tests/project_catalog -q` passed (5 tests).
- `python -m json.tool docs/specs/platform/portfolio.json >/dev/null` passed.
- A focused JSON assertion verified the achieved acceptance state, empty gaps, four evidence references, and that every referenced evidence path exists.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/project_catalog/test_resolver.py` | Unit | N/A (new) | ✅ Written | ✅ Passed | ✅ 5 cases | No behavior refactor needed |
| 1.2 | `tests/project_catalog/test_resolver.py` | Unit | N/A (new) | ✅ Written | ✅ Passed | ✅ 5 cases | No behavior refactor needed |
| 1.3 | `tests/project_catalog/test_resolver.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Passed | ✅ 5 cases | Wrapped an overlong test call; tests remained green |
| 1.4 | `tests/project_catalog/test_resolver.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Passed | ✅ 5 cases | No production refactor needed; implementation remained small and clear |
| 2.1 | `docs/specs/platform/portfolio.json` | Structural documentation | ✅ 5/5 | ✅ Written | ✅ Passed | ➖ Single | No refactor needed |
| 2.2 | `tests/project_catalog/test_resolver.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Passed | ➖ Single | No refactor needed |

## Deviations from design

`CatalogSourceContext` is returned as the design's declarative resolved source context; the resolver never executes a source provider.

One narrowing deviation exists, also carried in the frozen review ledger as a non-blocking WARNING: the implemented failure `details` payloads are narrower than the contract declared in `design.md`.

- `design.md` declares `ambiguous-resolution` details carry the matched identifier dimensions; the resolver returns `details={"record_ids": [...]}` only.
- `design.md` declares `invalid-catalog` details carry a deterministic reason code; the resolver returns `details={"record_id": ..., "invalid_fields": [...]}` only.

Every `spec.md` requirement still passes: the failure classes remain typed and distinguishable. Widening the payloads to the full design contract is deferred as a follow-up.

## Remaining tasks

None. All six persisted task checkboxes are marked `- [x]`.

## Workload / PR boundary

PR 1 remains the independently shippable pure-domain contract and resolver slice (344 source/test lines, below the 400-line budget). PR 2 is the completed, independently reversible evidence-only handoff: one semantic `portfolio.json` update plus focused final verification. Delivery remains `auto-chain` with `feature-branch-chain`; no onboarding, request orchestration, control-plane, tenancy, provider-selection, or data-stream scope entered PR 2.

## PR 2 status / next action

The native status consumed before implementation was authoritative OpenSpec `applyState: ready`, `nextRecommended: apply`, with the repo-local action context and allowed workspace root above. After the completed task checkboxes are observed by the dispatcher, the next phase is `verify`; archive remains deferred until a verify report exists.
