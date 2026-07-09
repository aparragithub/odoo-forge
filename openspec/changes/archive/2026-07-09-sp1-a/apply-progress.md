# Apply Progress: sp1-a

## Status
- Change: `sp1-a`
- Phase: `apply`
- Artifact store: `openspec`
- Delivery strategy: chained PRs
- Chain strategy: `stacked-to-main`
- Current slice boundary: PR 2 only — CLI wiring + boundary diagnostics + CLI tests + docs alignment/cleanup
- Prior dependency: PR 1 — core port + GHCR reference/error helpers + `odoo_forge_registry` adapter + unit tests
- Out of scope in this batch: commit/PR creation, verify/archive phases

## Structured Status Consumed
- `applyState`: `ready`
- `nextRecommended`: `apply`
- `actionContext.mode`: `repo-local`
- `allowedEditRoots`: `/home/aparra/Desarrollo/odoo-forge`
- Warnings: none; all edits stayed inside the authoritative workspace root

## Completed Tasks
- Marked `- [x] 1.1` in `tasks.md`
- Marked `- [x] 1.2` in `tasks.md`
- Marked `- [x] 2.1` in `tasks.md`
- Marked `- [x] 2.2` in `tasks.md`
- Marked `- [x] 2.3` in `tasks.md`
- Marked `- [x] 3.3` in `tasks.md`
- Marked `- [x] 4.1` in `tasks.md`
- Marked `- [x] 4.2` in `tasks.md`
- Marked `- [x] 3.1` in `tasks.md`
- Marked `- [x] 3.2` in `tasks.md`
- Marked `- [x] 4.3` in `tasks.md`
- Marked `- [x] 5.1` in `tasks.md`
- Marked `- [x] 5.2` in `tasks.md`

## Files Changed
- `src/odoo_forge/ports/image_registry_provider.py`
- `src/odoo_forge/image_registry/__init__.py`
- `src/odoo_forge/image_registry/errors.py`
- `src/odoo_forge/image_registry/reference.py`
- `src/odoo_forge_registry/__init__.py`
- `src/odoo_forge_registry/provider.py`
- `src/odoo_forge_cli/main.py`
- `tests/ports/test_image_registry_provider.py`
- `tests/adapters/test_registry_provider.py`
- `tests/cli/test_image_registry.py`
- `pyproject.toml`
- `openspec/changes/sp1-a/design.md`
- `openspec/changes/sp1-a/tasks.md`
- `openspec/changes/sp1-a/apply-progress.md`

## TDD Cycle Evidence
| Task(s) | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|
| 1.1, 4.1 | Added `tests/ports/test_image_registry_provider.py`; `uv run pytest tests/ports/test_image_registry_provider.py tests/adapters/test_registry_provider.py` failed with `ModuleNotFoundError` for the new port/core modules. | Added the port protocol plus pure GHCR reference/error core modules; focused pytest passed. | Port tests cover tag refs, digest refs, digest-required validation, unsupported registry, malformed refs, and protocol/signature conformance. | Kept pure parsing/error logic isolated under `odoo_forge.image_registry` and exported a minimal public surface. |
| 1.2, 2.1, 2.2, 3.3, 4.2 | Added `tests/adapters/test_registry_provider.py`; initial focused pytest failed with `ModuleNotFoundError` for `odoo_forge_registry`. | Added `odoo_forge_registry` adapter and `pyproject.toml` package/import-linter wiring; focused pytest passed. | Adapter tests cover success, auth failure, not-found failure, malformed-reference fail-fast, and subprocess timeout mapping. | Ran `ruff` cleanups on the new tests and kept subprocess/env/error classification adapter-local. |
| 2.3 | No production hook was added before tests; scope guard held during implementation. | Verified the new slice contains no CLI wiring, backend integration, pull behavior, or `project.lock` persistence hooks. | The focused suite exercises only pure core + adapter behaviors for this slice. | Preserved the slice boundary for the next chained PR. |
| 3.1, 3.2, 4.3 | Added `tests/cli/test_image_registry.py`; `uv run pytest tests/cli/test_image_registry.py` failed because `_make_image_registry_provider` and the `image-resolve` / `image-validate` commands did not exist. | Added `_make_image_registry_provider()`, `image-resolve`, `image-validate`, CLI pre-validation via `normalize_image_reference()`, and `RegistryError` exit-1 boundaries; focused CLI pytest passed. | CLI tests cover resolve success, validate success, auth failure, not-found failure, unsupported registry rejection, malformed digest rejection, and prove malformed/unsupported refs fail before the provider is called. | Removed an unused test import, kept command behavior minimal, and re-ran lint/import-boundary checks plus the broader CLI/registry suite. |
| 5.1, 5.2 | Added a docs-alignment expectation by updating the design delivery-slice notes after the CLI slice was implemented; no temporary scaffolding changes were needed before verification. | Updated `design.md` to reflect PR 1 vs PR 2 boundaries and verified no temp scaffolding remained after the full focused suite passed. | The second-slice evidence now matches the workload forecast split and the persisted task artifact shows all cleanup/doc tasks complete. | No extra cleanup code remained; kept the docs note minimal and left behavior unchanged. |

## Verification Evidence
- Safety net baseline before editing `src/odoo_forge_cli/main.py`: `uv run pytest tests/cli` → 48 passed.
- RED: `uv run pytest tests/cli/test_image_registry.py` → 6 failed because CLI image-registry wiring did not exist yet.
- GREEN: `uv run pytest tests/cli/test_image_registry.py` → 6 passed.
- REFACTOR verification: `uv run pytest tests/cli/test_image_registry.py` → 6 passed.
- Broader focused suite: `uv run pytest tests/cli tests/ports/test_image_registry_provider.py tests/adapters/test_registry_provider.py` → 71 passed.
- Static/import boundary checks: `uv run ruff check src/odoo_forge_cli/main.py tests/cli/test_image_registry.py`
- Import boundaries: `uv run lint-imports`
- Prior slice RED: `uv run pytest tests/ports/test_image_registry_provider.py tests/adapters/test_registry_provider.py` → failed during collection with missing-module errors before implementation.
- Prior slice GREEN: `uv run pytest tests/ports/test_image_registry_provider.py tests/adapters/test_registry_provider.py` → 17 passed.

## Design Deviations
- The registry adapter still normalizes/validates refs defensively, even though the CLI now pre-validates and normalizes before port calls. This is an intentional guardrail, not a scope deviation.
- `image-validate` prints `valid: <canonical-digest-ref>` rather than a bare `valid`, keeping the operator signal while preserving the canonical ref in the success output.

## Remaining Tasks
- None. `tasks.md` now shows every implementation task as `- [x]`.

## Workload / PR Boundary
- This batch implements only the second chained slice from the workload forecast.
- PR 2 boundary: `src/odoo_forge_cli/main.py`, `tests/cli/test_image_registry.py`, `openspec/changes/sp1-a/design.md`, and persisted task/progress artifacts.
- Review budget stayed aligned with the stacked-to-main plan by keeping core/adapter work in PR 1 and CLI/docs/test work in PR 2.
