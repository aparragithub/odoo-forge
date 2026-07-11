# Proposal: Redefine Platform Subprojects Around Outcomes

**Artifact parity ID:** `PR-PORTFOLIO-REDEFINITION-V5`

## Intent

Replace “one SP = one SDD change” with outcome epics having accountable ownership, aggregate acceptance, and implementation-sized delivery changes. Fresh SP-2 remains blocked until this documentation-only change is independently validated and intentionally archived.

## Scope

### In Scope
- Publish `portfolio-plan.json` as the normative, exhaustive portfolio: every approved SP, prerequisite, port, adapter, integration, workflow, decision, transition, transfer, edge, and future SDD-change. Narrative artifacts define intent and invariants but MUST NOT restate grouped inventories.
- Ship `docs/tools/platform_portfolio/validate.py` (stdlib) plus tests as the deterministic structural gate for that plan.
- Reclassify delivered SP-1 as `CAP-IMAGE-REGISTRY`; move only its unbuilt delivery remainder into delivery automation; split SP-10 without adding quota absent from its live source.

### Out of Scope
- Product code, runtime behavior, canonical runtime specifications, provider selection, or resolution of decisions preserved by `#6375`.
- Rewriting numeric SP briefs, founding bodies, or archived evidence.
- Migrating the docs tree (roadmap, briefs, HTML, Mermaid) into a live mirror — deferred to ordinary SDD when scheduled, not embedded here.

## Approach

Build the portfolio as concrete records and gate it with a committed deterministic validator instead of reviewer sampling. The plan carries the outcomes, capabilities, ports/adapters, integrations, workflows, future SDD changes, decisions, and old→new traceability; `validate.py` proves every reference resolves, scopes are well-formed, the dependency graph is acyclic, and the alias map is consistent. No per-slice migration machinery is embedded — that layer was the source of the review→fix loop and is dropped.

## Risks and Rollback

- **Ownership drift:** the validator checks exhaustive inventory, atomic transfers, and acyclic graph semantics on every change.
- **History/link drift:** numeric briefs, founding bodies, and archives stay byte-unchanged.
- **Scope creep:** re-embedding slice/manifest/activation machinery is rejected as the over-engineering this change cures.

Rollback reverts the plan and validator. Historical briefs and archives remain; SP-2 stays blocked until this change is reviewed and archived.

## Success Criteria

- [ ] `python docs/tools/platform_portfolio/validate.py --root .` reports 0 violations.
- [ ] Validator unit tests pass and demonstrably catch dangling references, unresolved transfer destinations, and dependency cycles.
- [ ] Every historical `SP-1`…`SP-10` reference resolves via `historical_alias_map`.
- [ ] Independent full-context review passes; ledger blocking rows are `verified|resolved`; then SP-2 unblocks.
