# Tasks: First Pipeline Adapter — GitHub Actions

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~260-320 |
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
| 1 | Full `odoo_forge_pipeline_github` adapter (transport seam, provider, mapping, packaging) | PR 1 | `uv run pytest tests/pipeline_github -q` | N/A — hermetic fake-transport tests only, no live GitHub Actions call | Delete `src/odoo_forge_pipeline_github/`, `tests/pipeline_github/`, revert `pyproject.toml` additions |

## Phase 1: Foundation — Transport Seam & Types

- [x] 1.1 (RED) `tests/pipeline_github/test_transport_protocol.py`: assert `GitHubActionsTransport` is `runtime_checkable` and a fake implementing its 4 methods passes `isinstance`.
- [x] 1.2 (GREEN) `src/odoo_forge_pipeline_github/transport.py`: define `GitHubActionsTransport` Protocol (`dispatch_workflow`, `latest_run_id`, `get_run_state`, `get_run_logs`) + real REST impl using injected token/session.
- [x] 1.3 `tests/pipeline_github/fakes.py`: `FakeGitHubActionsTransport` recording calls, configurable status/conclusion/logs, zero network access.

## Phase 2: Provider — Structural Conformance & Trigger

- [x] 2.1 (RED) `tests/pipeline_github/test_conformance.py`: `isinstance(GitHubActionsPipelineProvider(transport=fake, owner=..., repo=..., ref=...), PipelineProvider)` is `True`.
- [x] 2.2 (GREEN) `src/odoo_forge_pipeline_github/provider.py`: `GitHubActionsPipelineProvider.__init__` accepting `transport`, `owner`, `repo`, `ref`.
- [x] 2.3 (RED) `tests/pipeline_github/test_trigger.py`: `trigger(spec)` calls `dispatch_workflow(spec.definition, ref, spec.parameters)` then `latest_run_id(spec.definition, ref)`; asserts returned `PipelineRunRef.run_id` equals the fake's newest-run id (resolves design's deferred question: **newest-run correlation**, not input-marker).
- [x] 2.4 (GREEN) Implement `trigger()` in `provider.py` per 2.3.

## Phase 3: Status Mapping (All Six States)

- [x] 3.1 (RED) `tests/pipeline_github/test_status_mapping.py`: parametrized over the design's status/conclusion table — `queued→pending`, `in_progress→running`, `completed/success→succeeded`, `completed/failure→failed`, `completed/cancelled→canceled` (GitHub spelling), `completed/action_required|neutral|skipped|stale→unknown`, `completed/None→unknown`, unrecognized status→`unknown` fallback.
- [x] 3.2 (GREEN) `src/odoo_forge_pipeline_github/provider.py`: `_map_state(status, conclusion) -> PipelineRunState` covering every row; document `cancelled` (GH spelling) maps to `canceled` (neutral spelling) explicitly in a code comment.
- [x] 3.3 (GREEN) Wire `status(ref)` to call `transport.get_run_state(ref.run_id)` and return `PipelineRunStatus(state=_map_state(...))`.

## Phase 4: Logs & Neutrality

- [x] 4.1 (RED) `tests/pipeline_github/test_logs.py`: `logs(ref)` calls `transport.get_run_logs(ref.run_id)` and returns the fake's plain string unchanged.
- [x] 4.2 (GREEN) Implement `logs()` in `provider.py`.
- [x] 4.3 (RED) `tests/pipeline_github/test_neutrality.py`: assert `type(trigger(...))  is PipelineRunRef`, `type(status(...)) is PipelineRunStatus`, `type(logs(...)) is str`; no GitHub-specific attribute/type leaks.
- [x] 4.4 (GREEN) Adjust return statements if 4.3 fails (should already pass from Phases 2-4).

## Phase 5: Hermetic Guarantee & Package Export

- [x] 5.1 (RED) `tests/pipeline_github/test_hermetic.py`: exercise `trigger`, `status`, `logs` with the fake transport under a network-blocking fixture (e.g. monkeypatch `socket.socket` to raise); assert no error is raised (proves no direct network call).
- [x] 5.2 (GREEN) `src/odoo_forge_pipeline_github/__init__.py`: export `GitHubActionsPipelineProvider`.

## Phase 6: Packaging & Import-Linter Isolation

- [x] 6.1 Add `"src/odoo_forge_pipeline_github"` to `[tool.hatch.build.targets.wheel] packages` in `pyproject.toml`.
- [x] 6.2 Add `"odoo_forge_pipeline_github"` to `[tool.importlinter] root_packages` in `pyproject.toml`.
- [x] 6.3 Add new `[[tool.importlinter.contracts]]` forbidden contract: `source_modules = ["odoo_forge"]`, `forbidden_modules = ["odoo_forge_pipeline_github"]`, mirroring the `odoo_forge_registry` contract.
- [x] 6.4 (RED→GREEN) Run `uv run lint-imports`; confirm the new contract passes with zero violations.

## Phase 7: Full Verification Gate

- [x] 7.1 Run `uv run pytest` — full suite green, including all `tests/pipeline_github/` cases.
- [x] 7.2 Run `uv run lint-imports` — all contracts pass, including the new forbidden contract.
- [x] 7.3 Run `uv run mypy` — no type errors in `src/odoo_forge_pipeline_github/`.
- [x] 7.4 Run `uv run ruff check` — no lint violations.
