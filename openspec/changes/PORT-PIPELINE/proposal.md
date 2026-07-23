# Proposal: PORT-PIPELINE — Provider-Neutral Pipeline (CI) Port

## Intent

`odoo-forge` has no structural seam for delivery/CI pipelines. The portfolio marks
`PORT-PIPELINE` (PipelineProvider) as a READY port with no incoming hard edges. We
introduce the provider-neutral pipeline PORT CONTRACT now so downstream delivery work
can depend on a stable abstract interface. This unblocks planning without committing to a
CI engine: the concrete adapter (`CHG-FIRST-PIPELINE-ADAPTER`) is BLOCKED by the
unresolved decision `DPROV-CI` (which CI engine), so only the contract is in play here.

## Scope

### In Scope
- NEW `src/odoo_forge/ports/pipeline_provider.py` — `PipelineProvider` structural port
  (`Protocol`, `runtime_checkable`), mirroring `backend_provider.py`/`source_provider.py`
  style: module docstring, lazy annotations, `TYPE_CHECKING` domain-type imports, `__all__`.
- NEW provider-neutral domain types under `src/odoo_forge/pipeline/` if the contract needs
  them (e.g. abstract pipeline spec / run ref / status), CI-engine-agnostic only.
- NEW `tests/ports/test_pipeline_provider.py` — conformance/contract test mirroring
  `test_backend_provider.py` (structural `isinstance` pass, negative non-conforming case,
  docstring-boundary assertions).

### Out of Scope (non-goals)
- NO concrete adapter — `CHG-FIRST-PIPELINE-ADAPTER` stays BLOCKED on `DPROV-CI`.
- NO CI-engine-specific choices, names, YAML, or subprocess wiring (GitHub Actions, GitLab
  CI, etc.). The contract MUST stay provider-neutral.
- NO CLI wiring, no manifest/schema, credentials, or tenancy changes.

## Parallel-Safety Non-Collision Boundary

Runs IN PARALLEL with `CAP-TENANCY` (main checkout). To guarantee zero collision this
change touches ONLY the disjoint paths above, all inside this worktree, and MUST NOT modify:
`pyproject.toml` (stay under the registered `src/odoo_forge` package — no new top-level
`odoo_forge_*` package), `src/odoo_forge/manifest/schema.py`, `src/odoo_forge/credentials/*`,
`src/odoo_forge_cli/*`, `src/odoo_forge/tenancy/*`, or `ports/tenancy_provider.py`.
`src/odoo_forge/ports/__init__.py` is EMPTY and stays empty — no re-exports.

## Capabilities

### New Capabilities
- `pipeline-provider`: provider-neutral pipeline/CI port contract — abstract interface plus
  any CI-agnostic domain types and a conformance test.

### Modified Capabilities
- None.

## Approach

Add a `runtime_checkable` `Protocol` for `PipelineProvider` following the existing port
pattern (structural, interface-only, no adapter import). Keep methods and any domain types
expressed in provider-neutral vocabulary. Prove satisfiability with a structural fake in the
port test; assert the neutrality boundary in a docstring test.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/ports/pipeline_provider.py` | New | Port interface |
| `src/odoo_forge/pipeline/` | New (if needed) | Neutral domain types |
| `tests/ports/test_pipeline_provider.py` | New | Conformance test |
| `openspec/changes/PORT-PIPELINE/` | New | SDD artifacts |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Contract leaks CI-engine assumptions | Med | Neutral vocabulary; docstring-boundary test |
| Over-building ahead of `DPROV-CI` | Med | Contract-only scope; adapter explicit non-goal |
| Path collision with `CAP-TENANCY` | Low | Disjoint-path allowlist; empty `ports/__init__.py` |

## Rollback Plan

Delete `src/odoo_forge/ports/pipeline_provider.py`, `src/odoo_forge/pipeline/`, and
`tests/ports/test_pipeline_provider.py`. No shared files touched, so revert is isolated and
leaves no dangling references.

## Dependencies

- `DPROV-CI` decision — required only for the downstream adapter, NOT for this contract.

## Success Criteria

- [ ] `PipelineProvider` port exists, interface-only, mirroring existing port style.
- [ ] Conformance test passes (`uv run pytest tests/ports/test_pipeline_provider.py`).
- [ ] No CI-engine-specific names/choices anywhere in the contract.
- [ ] No file outside the disjoint allowlist is modified.
- [ ] Delivers as a single small PR (contract only).
