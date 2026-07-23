# Design: First Pipeline Adapter — GitHub Actions

## Technical Approach

Add an isolated adapter package `src/odoo_forge_pipeline_github/` that implements the
`PipelineProvider` port (`src/odoo_forge/ports/pipeline_provider.py`) and returns only the
neutral types in `src/odoo_forge/pipeline/types.py`. The provider depends on the port + neutral
types only; all network I/O lives behind an injected transport Protocol, mirroring the
`odoo_forge_registry` (GHCR) layering and its packaging/import-linter isolation. Fulfils the
`github-actions-pipeline-adapter` capability; port and core stay unchanged.

## Architecture Decisions

### Decision: Injectable transport Protocol (not subprocess)

**Choice**: Constructor-inject a `GitHubActionsTransport` Protocol; the real REST implementation is
one class, a fake is used in tests. The provider never touches `httpx`/network directly.
**Alternatives considered**: (a) GHCR's subprocess seam — rejected, no CLI mediates the Actions REST
API; (b) provider calls an HTTP client inline — rejected, breaks hermetic tests and neutrality.
**Rationale**: Enables hermetic unit tests (no live network) and keeps GitHub vocabulary contained
in the transport layer.

### Decision: Auth/token handoff via the real transport only

**Choice**: The token is supplied to the real transport's constructor from the existing
config/secret handling; the provider is auth-agnostic and the fake transport needs no token.
**Alternatives considered**: token on the provider or a new secrets store — rejected (invents a
mechanism; couples the provider to auth).
**Rationale**: Single seam owns credentials; no new secrets mechanism introduced.

### Decision: Run correlation after dispatch

**Choice**: `workflow_dispatch` returns 204 (no run id). After dispatch, query the newest run for the
workflow+ref and adopt its id into `PipelineRunRef.run_id`.
**Rationale**: Known GitHub limitation; correlation is documented as a gotcha (see Open Questions).

## Data Flow

    PipelineRunSpec ─trigger()→ Provider ─dispatch_workflow()→ Transport ─→ GitHub REST
                                     │←── latest_run() ─────────────┘
                                     └──→ PipelineRunRef(run_id)

    PipelineRunRef ─status()→ Provider ─get_run_state()→ Transport → (status, conclusion)
                                     └─ map → PipelineRunStatus(state)
    PipelineRunRef ─logs()→ Provider ─get_run_logs()→ Transport → str

`spec.definition` = workflow filename (e.g. `ci.yml`); `spec.parameters` = `workflow_dispatch`
inputs. Repo coordinates (`owner/repo/ref`) are provider construction args, not neutral spec fields.

## Status Mapping (GitHub → neutral `PipelineRunState`)

| GH `status` | GH `conclusion` | Neutral state |
|---|---|---|
| `queued`, `requested`, `waiting`, `pending` | any / null | `pending` |
| `in_progress` | null | `running` |
| `completed` | `success` | `succeeded` |
| `completed` | `failure`, `timed_out`, `startup_failure` | `failed` |
| `completed` | `cancelled` | `canceled` |
| `completed` | `action_required`, `neutral`, `skipped`, `stale` | `unknown` |
| `completed` | null / unrecognized | `unknown` |
| anything unrecognized | * | `unknown` (fallback) |

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge_pipeline_github/__init__.py` | Create | Export `GitHubActionsPipelineProvider` |
| `src/odoo_forge_pipeline_github/provider.py` | Create | Provider + status-mapping function |
| `src/odoo_forge_pipeline_github/transport.py` | Create | `GitHubActionsTransport` Protocol, real REST impl, GH-shaped model |
| `pyproject.toml` | Modify | Add package to wheel `packages`, `root_packages`, new forbidden contract |
| `tests/pipeline_github/` | Create | Conformance, mapping-table, neutrality, dispatch tests (fake transport) |

## Interfaces / Contracts

```python
@runtime_checkable
class GitHubActionsTransport(Protocol):
    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> None: ...
    def latest_run_id(self, workflow: str, ref: str) -> str: ...
    def get_run_state(self, run_id: str) -> tuple[str, str | None]: ...  # (status, conclusion)
    def get_run_logs(self, run_id: str) -> str: ...

class GitHubActionsPipelineProvider:  # structurally satisfies PipelineProvider
    def __init__(self, *, transport: GitHubActionsTransport, owner: str, repo: str, ref: str): ...
```

GH JSON parsing stays inside the transport; the provider maps `(status, conclusion)` → neutral state.

## pyproject.toml Additions

- `[tool.hatch.build.targets.wheel] packages` += `"src/odoo_forge_pipeline_github"`.
- `[tool.importlinter] root_packages` += `"odoo_forge_pipeline_github"`.
- New forbidden contract:

```toml
[[tool.importlinter.contracts]]
name = "Core never imports the pipeline github adapter"
type = "forbidden"
source_modules = ["odoo_forge"]
forbidden_modules = ["odoo_forge_pipeline_github"]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `isinstance(provider, PipelineProvider)` | runtime_checkable structural conformance |
| Unit | Every status-mapping row incl. `unknown` fallback | parametrized over the table, fake transport |
| Unit | Return values are neutral types only (no GH fields) | assert types / no leakage |
| Unit | trigger dispatch + run correlation; logs passthrough | fake transport, no network |
| Contract | import-linter forbidden contract passes | `lint-imports` in CI |

## Threat Matrix

Process-integration boundary present (network/REST), but shell/git/PR rows do not apply:

| Boundary | Applicability |
|---|---|
| Documentation-like paths | N/A: no file classification |
| Git repository selection | N/A: no git invocation; repo coords are plain constructor args |
| Commit state | N/A: no commits |
| Push state | N/A: no push |
| PR commands | N/A: no PR automation |

Network integration is contained: the injected transport is the sole I/O seam; unit tests use a fake,
so no live network. Auth failures surface as transport errors and are not masked by the provider.

## Migration / Rollout

No migration. Additive package; revert = delete package + tests and undo `pyproject.toml` additions.

## Open Questions

- [ ] Run-correlation strategy after `workflow_dispatch` (newest-run vs. input marker) — pick one in tasks.
- [ ] Logs format: raw text vs. decoded zip — transport returns `str`; decoding detail deferred to tasks.
