# Design: PORT-PIPELINE — Provider-Neutral Pipeline (CI) Port

## Technical Approach

Introduce a `runtime_checkable` structural `Protocol`, `PipelineProvider`, plus a
small set of CI-engine-agnostic domain types, and a conformance + neutrality test.
Interface only — no adapter, no CI engine chosen (blocked on `DPROV-CI`). The port
mirrors `backend_provider.py` (structural port) and `backend/status.py` +
`backend/plan.py` (pure pydantic domain types, zero I/O). Realizes the proposal's
`pipeline-provider` capability as a single small contract-only PR.

## Scope Boundary (authoritative, parallel-safe)

Touches ONLY: `src/odoo_forge/ports/pipeline_provider.py`,
`src/odoo_forge/pipeline/__init__.py`, `src/odoo_forge/pipeline/types.py`,
`tests/ports/test_pipeline_provider.py`. MUST NOT modify `pyproject.toml`,
`manifest/schema.py`, `credentials/*`, `src/odoo_forge_cli/*`, `tenancy/*`,
`ports/tenancy_provider.py`. `ports/__init__.py` stays EMPTY — no re-exports.

## Architecture Decisions

| Decision | Choice | Alternatives rejected | Rationale |
|----------|--------|-----------------------|-----------|
| Port shape | `runtime_checkable` `Protocol`, interface-only | `ABC` base class | Matches every existing port (`backend`, `source`); structural conformance, no inheritance coupling to a future adapter |
| Method surface | 3 neutral verbs: `trigger` / `status` / `logs` | Rich multi-method engine API | Proposal's three concerns (definition-trigger, status query, output retrieval); minimal seam avoids over-building ahead of `DPROV-CI` |
| Domain types location | New `src/odoo_forge/pipeline/` package (`types.py`) | Inline in port module; reuse `backend.*` | Ports keep types in a sibling domain module (`backend.status`/`backend.plan`); pipeline concepts are distinct from backend |
| Types style | pydantic `BaseModel` + `Literal` state enum | dataclasses / raw dicts | `backend/status.py` uses `BaseModel` + `Literal` (`RoleState`); consistency |
| Neutrality guarantee | Test-enforced denylist over the public surface | Convention/docstring only | Neutrality is a NORMATIVE invariant; a boundary test makes leaks fail CI |
| Annotation strategy | `from __future__ import annotations` + `TYPE_CHECKING` imports in port | Eager imports | Mirrors `backend_provider.py`; `runtime_checkable` inspects method NAMES only, so lazy annotations keep `isinstance` valid |

## Data Flow

    caller ──trigger(PipelineRunSpec)──▶ PipelineProvider ──▶ PipelineRunRef
      │                                                            │
      ├──status(PipelineRunRef)──▶ PipelineProvider ──▶ PipelineRunStatus
      └──logs(PipelineRunRef)────▶ PipelineProvider ──▶ str

All types are provider-neutral values; the (future) adapter maps them to a concrete
engine. No I/O in this slice.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge/ports/pipeline_provider.py` | Create | `PipelineProvider` Protocol; `TYPE_CHECKING` imports of `pipeline.types`; `__all__` |
| `src/odoo_forge/pipeline/__init__.py` | Create | Empty package marker |
| `src/odoo_forge/pipeline/types.py` | Create | `PipelineRunSpec`, `PipelineRunRef`, `PipelineRunState`, `PipelineRunStatus`; `__all__` |
| `tests/ports/test_pipeline_provider.py` | Create | Conformance (pass/fail), docstring boundary, neutrality denylist |

## Interfaces / Contracts

```python
# ports/pipeline_provider.py
@runtime_checkable
class PipelineProvider(Protocol):
    def trigger(self, spec: PipelineRunSpec) -> PipelineRunRef:
        """Start a run from a provider-neutral definition; return an opaque run handle."""
        ...
    def status(self, ref: PipelineRunRef) -> PipelineRunStatus:
        """Report `ref`'s current neutral run state."""
        ...
    def logs(self, ref: PipelineRunRef) -> str:
        """Return `ref`'s accumulated output text."""
        ...

# pipeline/types.py
PipelineRunState = Literal[
    "pending", "running", "succeeded", "failed", "canceled", "unknown"
]

class PipelineRunSpec(BaseModel):
    definition: str                      # opaque neutral reference to a run definition
    parameters: dict[str, str] = {}

class PipelineRunRef(BaseModel):
    run_id: str

class PipelineRunStatus(BaseModel):
    state: PipelineRunState
```

Vocabulary is deliberately neutral: `run`, `trigger`, `status`, `logs`, `definition`,
`parameters`, `state`. No engine terms (no `workflow`, `job`, `stage`, `action`,
`runner`, `pipeline yaml`, or vendor names).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Contract | Structural fake satisfies `PipelineProvider` | `isinstance(fake, PipelineProvider)` with `object`-typed params (mirrors `test_backend_provider.py`) |
| Contract | Missing a method fails conformance | `not isinstance(_MissingLogs(), PipelineProvider)` |
| Boundary | Method docstrings document neutral contract | assert key docstring phrases present |
| Neutrality | No CI-engine names in public surface | Scan port + `types.py` source, `__all__`, method names, docstrings against a denylist: `github`, `gitlab`, `jenkins`, `circleci`, `travis`, `azure`, `buildkite`, `teamcity`, `argo`, `tekton`, `drone`, `actions`, `workflow`, `runner`, `yaml` — assert none present (case-insensitive) |

All tests live in `tests/ports/test_pipeline_provider.py`. Command:
`uv run pytest tests/ports/test_pipeline_provider.py`. Strict TDD: neutrality and
conformance tests are written RED first.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary. Interface + pure types only; the
adapter that would introduce process integration is an explicit non-goal (`DPROV-CI`).

## Migration / Rollout

No migration required. Additive new files only. Rollback = delete the four new files;
no shared file touched, no dangling references.

## Success Criteria

- [ ] `PipelineProvider` port exists, interface-only, mirroring existing port style.
- [ ] Conformance + neutrality tests pass (`uv run pytest tests/ports/test_pipeline_provider.py`).
- [ ] No CI-engine-specific name anywhere in the public surface (test-enforced).
- [ ] No file outside the disjoint allowlist modified; `ports/__init__.py` still empty.
- [ ] Single small PR (contract only), well under the 400-line review budget.

## Open Questions

- [ ] Whether a `cancel(ref)` method belongs in the seam — deferred; add only when a
  concrete consumer needs it (avoid speculative surface ahead of `DPROV-CI`).
