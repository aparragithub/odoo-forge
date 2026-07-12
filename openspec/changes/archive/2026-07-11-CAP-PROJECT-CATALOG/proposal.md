# Proposal: CAP-PROJECT-CATALOG

## Intent

Define the contract for authoritative client/project resolution so downstream flows can consume one accepted project-catalog result instead of re-implementing manifest lookup, source context selection, data-policy defaults, and target defaults.

## Scope

### In Scope
- Define the input identifiers and lookup rules for resolving a client/project request.
- Define the authoritative outputs: manifest reference, source context, data-policy default, and target default.
- Define conflict, fallback, and failure rules for ambiguous, missing, or invalid catalog entries.
- Define acceptance evidence for `AC-CAP-PROJECT-CATALOG-READY`.

### Out of Scope
- Environment-request orchestration, onboarding flow logic, or control-plane persistence.
- Tenancy, RBAC, approval, audit, or provider selection policy.
- Data-artifact capture/restore, database lifecycle, anonymization, or runtime cutover.
- Direct adapter implementation for remote, identity, pipeline, or database concerns.

## Capabilities

### New Capabilities
- `project-catalog-resolution`: normative contract for authoritative client/project lookup and default resolution.

### Modified Capabilities
- None.

## Approach

Use a contract-first proposal anchored in the portfolio authority and existing manifest/source/workspace foundations. The change should introduce one explicit catalog boundary that resolves project/client intent into stable downstream inputs while keeping workflow, persistence, and provider concerns outside this capability.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/changes/CAP-PROJECT-CATALOG/` | Modified | Proposal, later specs/design/tasks for this capability |
| `openspec/specs/` | New | Canonical capability spec for project catalog resolution |
| `docs/specs/platform/portfolio.json` | Modified | Acceptance evidence and capability handoff updates |
| `src/odoo_forge/manifest/` | Referenced | Existing manifest structures inform the resolution boundary |
| `src/odoo_forge/ports/source_provider.py` | Referenced | Existing source-context primitives consumed by the future contract |
| `src/odoo_forge/ports/workspace_provider.py` | Referenced | Existing workspace/default consumers inform downstream shape |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope creeps into onboarding/request workflows | High | Keep this change limited to lookup/default contract only |
| Control-plane or tenancy semantics leak into the catalog | Med | Make ownership boundaries explicit in the spec |
| Different consumers invent different fallback/default rules | High | Standardize one authoritative result shape and failure model |

## Rollback Plan

Revert the proposal/spec artifacts and leave downstream consumers blocked on `AC-CAP-PROJECT-CATALOG-READY` until a corrected catalog contract is approved.

## Dependencies

- `docs/specs/platform/portfolio.json`
- `openspec/specs/platform-subproject-governance/spec.md`
- `openspec/specs/platform-portfolio-documentation-integrity/spec.md`
- `src/odoo_forge/manifest/schema.py`
- `src/odoo_forge/ports/source_provider.py`
- `src/odoo_forge/ports/workspace_provider.py`

## Success Criteria

- [ ] The contract defines which identifiers select a project/client record and how ambiguity is handled.
- [ ] The contract defines the authoritative outputs: manifest reference, source context, data-policy default, and target default.
- [ ] Ownership boundaries are explicit between project catalog, tenancy, control plane, and downstream workflows.
- [ ] `AC-CAP-PROJECT-CATALOG-READY` evidence is sufficient for downstream onboarding/request flows without absorbing their implementation.
