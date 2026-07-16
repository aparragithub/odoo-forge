# Proposal: Refresh Platform Roadmap After Stabilization

## Intent

Reconcile current platform guidance with HEAD after database-adapter and materialized-state stabilization. The result will give maintainers one evidence-backed roadmap, accurate implementation views, and an unambiguous active OpenSpec inventory without rewriting history.

## Scope

### In Scope
- Classify artifacts: **authoritative** sources may be edited; **derived** files change only through their source workflow; **historical/protected** archives, receipts, and dated documents remain immutable.
- Reconcile these document families: `docs/specs/2026-07-14-stabilization-roadmap.md`, `docs/specs/platform/portfolio.json` plus its validator/tests, `README.md`, and the current implementation Mermaid/SVG/Spanish guide.
- Define and verify ownership/source policy for `docs/specs/platform/platform-architecture.html`; update it to HEAD only through its proven authoritative source, never by hand if generated.
- Inventory active OpenSpec as this change plus blocked `sp-data-environments`; archive `CHG-FIRST-DATABASE-ADAPTER` as superseded while preserving a traceable pointer to the final archived implementation.

### Out of Scope
- Changes to runtime code, normative adapter behavior, or canonical archived evidence.
- Wholesale translation of the Spanish implementation guide.
- Technical Unit 4 registry/Git/workspace runtime-risk recheck; it requires a later SDD change.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `platform-portfolio-documentation-integrity`: require evidence-backed current guidance, explicit artifact ownership, immutable history, and deterministic derived-artifact validation.

## Approach

Apply authority-first reconciliation. Treat portfolio data, canonical specs, archived receipts, and the stabilization roadmap within their declared domains; derive SVG only from Mermaid with `render-current-implementation.sh`. For `S62`, retain references only when existing verifiable evidence resolves them; otherwise remove false references and report the gap—never fabricate evidence. Deliver forced chained slices, each ≤400 authored changed lines: (1) inventory/portfolio/roadmap, (2) README/guide/Mermaid, (3) generated SVG/HTML and validation receipts.

## Affected Areas

| Area | Impact |
|---|---|
| Current roadmap, portfolio, validator | Modified |
| README and implementation diagram family | Modified/regenerated |
| Architecture HTML ownership chain | Verified, then modified/regenerated |
| Active OpenSpec inventory | Modified by supersession archive |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Evidence or history is misrepresented | Medium | Require receipts; preserve protected artifacts |
| Generated output is nondeterministic/oversized | Medium | Pinned renderer, byte comparison, isolated chain slice |

## Rollback Plan

Revert each chain slice independently; restore the stale active-change location if archival fails. Never roll back by editing archived evidence or generated files directly.

## Dependencies

- Existing archived implementation receipts and a verified HTML ownership/source policy.

## Success Criteria

- [ ] Current claims and active inventory match HEAD; stale change is archived as superseded with traceability.
- [ ] `S62` references resolve to existing evidence or are removed without fabrication.
- [ ] Portfolio validator/tests, stale-claim searches, OpenSpec inventory checks, and `render-current-implementation.sh --check` pass.
- [ ] Every delivery slice stays within 400 authored changed lines.
