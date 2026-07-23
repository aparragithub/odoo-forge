# Tasks: Wire the GitHub Actions Pipeline Adapter into the CLI

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~160-220 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Composition-root factory + `pipeline` command module + registration + tests | PR 1 | `uv run pytest tests/cli/test_pipeline.py -q` | N/A — hermetic `CliRunner` + monkeypatched `_composition._make_pipeline_provider`, no live GitHub Actions call | Delete `src/odoo_forge_cli/commands/pipeline.py` and `tests/cli/test_pipeline.py`; revert the factory/error-class hunk in `_composition.py` and the two lines in `main.py` |

## Phase 1: Foundation — Composition-Root Factory

- [x] 1.1 (RED) `tests/cli/test_composition_pipeline.py` (or add to existing `_composition` test module): missing any of `FORGE_PIPELINE_GITHUB_{TOKEN,OWNER,REPO,REF}` raises `PipelineConfigurationError` naming that exact var; message never contains a value.
- [x] 1.2 (RED) same file: all four env vars present -> `_make_pipeline_provider()` returns a `GitHubActionsPipelineProvider` constructed with a `GitHubActionsRestTransport`.
- [x] 1.3 (GREEN) `src/odoo_forge_cli/_composition.py`: add `PipelineConfigurationError(RuntimeError)`, `_require_pipeline_env(name)`, `_make_pipeline_provider()` per design's `Interfaces / Contracts` block.

## Phase 2: Core Implementation — `trigger` / `status` Commands

- [x] 2.1 (RED) `tests/cli/test_pipeline.py`: `pipeline-trigger --workflow X` success path — fake provider's `trigger` called with a `PipelineRunSpec` derived from args; bare `run_ref.run_id` echoed; exit 0.
- [x] 2.2 (RED) same file: repeatable `--param KEY=VALUE --param KEY2=VALUE2` maps into `PipelineRunSpec.parameters` dict.
- [x] 2.3 (RED) same file: malformed `--param` (no `=`) fails fast with a single `error: ...` line, exit 1, and the fake provider's call log stays empty (never reaches `trigger`).
- [x] 2.4 (RED) same file: `pipeline-status --run-id X` success path — fake provider's `status` called with the given ref; bare `status.state` echoed; exit 0.
- [x] 2.5 (RED) same file: provider raising `OSError`/`RuntimeError`/`ValueError` from either command -> exactly one `error: ...` line, exit 1, no traceback.
- [x] 2.6 (RED) same file: token value configured via env var never appears in `result.output` (stdout or stderr) on success or error path.
- [x] 2.7 (GREEN) `src/odoo_forge_cli/commands/pipeline.py`: implement `trigger`, `status`, `register(app)` per design's `Interfaces / Contracts` block — catch `(OSError, RuntimeError, ValueError)` around factory + provider call into one `error: ...` line + `typer.Exit(code=1)`.

## Phase 3: Integration — Registration

- [x] 3.1 (RED) same test file: `runner.invoke(app, ["--help"])` on the root `forge` app lists `pipeline-trigger` and `pipeline-status`.
- [x] 3.2 (GREEN) `src/odoo_forge_cli/main.py`: import `pipeline` and call `pipeline.register(app)`, same pattern as `backend`/`image`/`maintenance`/`manifest`.

## Phase 4: Full Verification Gate

- [x] 4.1 Run `uv run pytest tests/cli/test_pipeline.py -q` — all new cases green.
- [x] 4.2 Run `uv run pytest` — full suite green, no regressions.
- [x] 4.3 Run `uv run lint-imports` — existing contracts pass unchanged (no new contract needed per design).
- [x] 4.4 Run `uv run mypy` — no type errors in `_composition.py` or `commands/pipeline.py`.
- [x] 4.5 Run `uv run ruff check` — no lint violations.
