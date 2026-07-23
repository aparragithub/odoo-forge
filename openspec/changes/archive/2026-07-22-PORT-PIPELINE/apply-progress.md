# Apply Progress: PORT-PIPELINE

Status: complete (all tasks done, single PR)

## Summary

Implemented the provider-neutral `PipelineProvider` structural port plus
neutral domain types, following strict TDD (RED -> GREEN -> REFACTOR).

## Files created

- `src/odoo_forge/pipeline/__init__.py` — empty package marker
- `src/odoo_forge/pipeline/types.py` — `PipelineRunState`, `PipelineRunSpec`,
  `PipelineRunRef`, `PipelineRunStatus`
- `src/odoo_forge/ports/pipeline_provider.py` — `runtime_checkable`
  `PipelineProvider` Protocol (`trigger`/`status`/`logs`), `TYPE_CHECKING`-only
  import of `pipeline.types`, no adapter import
- `tests/ports/test_pipeline_provider.py` — conformance, non-conformance,
  happy-path, unknown-run, docstring-boundary, CI-engine denylist, and
  no-adapter-import tests

## TDD evidence

- RED: `uv run pytest tests/ports/test_pipeline_provider.py` failed at
  collection with `ImportError: cannot import name 'pipeline' from
  'odoo_forge'` before any implementation existed.
- GREEN: after adding the three implementation files, all 7 tests passed.
- One self-correction during GREEN: the initial `test_no_adapter_import_in_pipeline_provider`
  scanned raw module *source text* for the substring `"adapter"`, which
  false-positived on the module's own docstring prose ("no adapter in this
  slice"). Fixed by parsing the module with `ast` and checking only actual
  `import`/`from ... import` module names, which is what the spec's
  "inspect import statements" scenario actually requires.

## Verification (real output)

- `uv run pytest tests/ports/test_pipeline_provider.py` — 7 passed
- `uv run pytest` (full suite) — 908 passed, 17 deselected
- `uv run lint-imports` — 6 kept, 0 broken
- `git status --porcelain` — only 3 untracked paths:
  `src/odoo_forge/pipeline/`, `src/odoo_forge/ports/pipeline_provider.py`,
  `tests/ports/test_pipeline_provider.py`
- `git diff --stat` — empty (no tracked file was modified)
- `src/odoo_forge/ports/__init__.py` — confirmed 0 bytes, unchanged, no
  re-exports added
- No edits to `pyproject.toml`, `manifest/schema.py`, `credentials/*`,
  `src/odoo_forge_cli/*`, `tenancy/*`, `ports/tenancy_provider.py`

## Parallel-safety confirmation

Only the four allowlisted paths (plus `tasks.md`/`apply-progress.md`) were
touched. No file shared with the concurrent CAP-TENANCY change (in the main
checkout) was modified in this worktree.

Not committed — orchestrator handles git per instructions.
