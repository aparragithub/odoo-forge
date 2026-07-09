# Apply Progress: platform-image-registry-provider

## Status
- Change: `platform-image-registry-provider`
- Phase: `apply`
- Artifact store: `hybrid`
- Delivery strategy: `force-chained`
- Chain strategy: `stacked-to-main`
- Current work unit: whole-change cleanup / traceability pass
- Prior dependency: PR 1 complete and frozen
- Out of scope in this batch: commit/PR creation, verify/archive phases, `PublishedLayer` cleanup

## Structured Status Consumed
- `applyState`: `ready`
- `nextRecommended`: `apply`
- `actionContext.mode`: `repo-local`
- `allowedEditRoots`: `/home/aparra/Desarrollo/odoo-forge`
- Warnings: none; edits stayed inside the authoritative workspace root

## Completed Tasks
- Marked `1.1`-`3.3` complete in `tasks.md`
- Marked `4.1` and `4.2` complete in `tasks.md`
- Tightened `docs/specs/platform/SP-1-image-registry-provider.md` to the implemented `publish` / `pull` / `resolve_digest` / `exists` contract
- Removed legacy `resolve()` / `validate()` compatibility glue from `src/odoo_forge_registry/provider.py`
- Updated adapter tests to call `resolve_digest()` directly and assert the bridge is gone
- Consolidated the strict-TDD record so it reads as one whole-change pass

## Files Changed
- `docs/specs/platform/SP-1-image-registry-provider.md`
- `src/odoo_forge_registry/provider.py`
- `tests/adapters/test_registry_provider.py`
- `openspec/changes/platform-image-registry-provider/tasks.md`
- `openspec/changes/platform-image-registry-provider/apply-progress.md`

## Whole-Change TDD Evidence
| Area | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|
| 1.1-1.3 foundation | prior slice coverage | Port/types/errors were already covered by contract tests | Core contract and value types passed | Multiple contract cases exercised | Clean and stable |
| 2.1-2.4 adapter + CLI | `uv run pytest tests/adapters/test_registry_provider.py tests/cli/test_image_registry.py` → 31 passed | Added publish/pull/exists mapping tests before implementation | GHCR-first adapter and CLI surface passed | Push/pull/exists and error-path coverage | Ruff cleanup |
| 3.1-3.3 verification | same focused suite + boundary reruns | Added boundary/regression coverage | All relevant focused tests passed | Added present/absent and `project.lock` boundary cases | Mypy/ruff clean |
| 4.1-4.2 cleanup | `uv run pytest tests/adapters/test_registry_provider.py tests/cli/test_image_registry.py` → 32 passed after cleanup | Added approval coverage for the legacy bridge removal | Removed compatibility glue and updated the doc | Triangulation skipped: cleanup has one valid end state | Reduced adapter surface |

## Verification Evidence
- `uv run pytest tests/adapters/test_registry_provider.py tests/cli/test_image_registry.py` → 32 passed
- `uv run ruff check src/odoo_forge_registry/provider.py tests/adapters/test_registry_provider.py` → passed
- `uv run mypy src tests` → success

## Remaining Tasks
- None in this batch; ready for verify/review after rerun

## Workload / PR Boundary
- Mode: `chained PR slice`
- Current work unit: cleanup / traceability pass
- Boundary: docs alignment, legacy bridge removal, and progress consolidation only
- Estimated review budget impact: minimal

## Status
12/12 tasks complete. Ready for verify.
