# Tasks: PORT-PIPELINE — Provider-Neutral Pipeline (CI) Port

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-220 (4 new files: 2 tiny modules, 1 empty `__init__.py`, 1 test file) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Contract-only port + neutral types + conformance/neutrality tests | PR 1 (single) | `uv run pytest tests/ports/test_pipeline_provider.py` | N/A — pure interface/types, no I/O, no adapter to exercise | Delete the 4 new files; no shared file touched, no dangling references |

## Phase 1: RED — Failing Tests First

- [x] 1.1 Create `tests/ports/test_pipeline_provider.py` with a structurally-conforming fake class (`trigger`, `status`, `logs` methods, `object`-typed params) and assert `isinstance(fake, PipelineProvider)` — MUST fail (import error) since `PipelineProvider` doesn't exist yet.
- [x] 1.2 In the same test file, add a fake missing `logs()` and assert `not isinstance(fake, PipelineProvider)`.
- [x] 1.3 Add trigger→status→logs happy-path test using the fake provider and neutral types (`PipelineRunSpec`, `PipelineRunRef`, `PipelineRunStatus`), asserting return shapes carry no CI-engine vocabulary.
- [x] 1.4 Add "unknown run" scenario test: querying status for an unrecognized `PipelineRunRef` is allowed to raise or return a distinct state without requiring a CI-engine-specific error type.
- [x] 1.5 Add docstring-boundary test asserting key neutral docstring phrases are present on `trigger`/`status`/`logs`.
- [x] 1.6 Add the CI-engine denylist neutrality test: scan source text of `pipeline_provider.py` and `pipeline/types.py` for tokens `github`, `gitlab`, `jenkins`, `circleci`, `travis`, `azure`, `buildkite`, `teamcity`, `argo`, `tekton`, `drone`, `actions`, `workflow`, `runner`, `yaml` (case-insensitive) — assert none present.
- [x] 1.7 Add no-adapter-import test: inspect `pipeline_provider.py`'s import statements and assert no concrete CI adapter or CI-engine-specific package is imported.
- [x] 1.8 Run `uv run pytest tests/ports/test_pipeline_provider.py` — confirm all tests fail with `ImportError`/`ModuleNotFoundError` (RED baseline).

## Phase 2: GREEN — Minimal Implementation

- [x] 2.1 Create `src/odoo_forge/pipeline/__init__.py` as an empty package marker.
- [x] 2.2 Create `src/odoo_forge/pipeline/types.py`: `PipelineRunState` (`Literal["pending","running","succeeded","failed","canceled","unknown"]`), `PipelineRunSpec(BaseModel)` (`definition: str`, `parameters: dict[str, str] = {}`), `PipelineRunRef(BaseModel)` (`run_id: str`), `PipelineRunStatus(BaseModel)` (`state: PipelineRunState`); define `__all__`.
- [x] 2.3 Create `src/odoo_forge/ports/pipeline_provider.py`: `from __future__ import annotations`; `TYPE_CHECKING`-guarded import of `pipeline.types`; `@runtime_checkable class PipelineProvider(Protocol)` with `trigger(spec) -> PipelineRunRef`, `status(ref) -> PipelineRunStatus`, `logs(ref) -> str`, neutral docstrings on each method; define `__all__`. No adapter import.
- [x] 2.4 Run `uv run pytest tests/ports/test_pipeline_provider.py` — confirm all tests pass (GREEN).

## Phase 3: REFACTOR — Cleanup and Verification

- [x] 3.1 Review method/docstring wording in `pipeline_provider.py` and `pipeline/types.py` for minimality and consistency with `backend_provider.py` / `backend/status.py` style; no behavior change.
- [x] 3.2 Confirm `src/odoo_forge/ports/__init__.py` is unchanged and still empty (no re-exports added).
- [x] 3.3 Confirm no edits touch `pyproject.toml`, `manifest/schema.py`, `credentials/*`, `src/odoo_forge_cli/*`, `tenancy/*`, or `ports/tenancy_provider.py`.
- [x] 3.4 Run `uv run lint-imports` — confirm no import-boundary violation introduced.
- [x] 3.5 Re-run `uv run pytest tests/ports/test_pipeline_provider.py` — confirm still GREEN after cleanup.
