# Archive Report: Redefine Platform Subprojects Around Outcomes

**Change:** `platform-subproject-redefinition`
**Archived:** 2026-07-10
**Result:** PASS — intentional completion

## Outcome

The ambiguous "one SP = one SDD change" model was replaced with an outcome-first
portfolio. The normative portfolio (`portfolio-plan.json`) — 55 items, 12 open
decisions, 93 concern transfers, 73 dependency edges, and full old→new
traceability — was promoted to its living home at
`docs/specs/platform/portfolio.json`. A pure-standard-library deterministic
validator (`docs/tools/platform_portfolio/validate.py`) gates its structural
integrity.

## Artifacts

| Artifact | Destination |
|---|---|
| Living portfolio | `docs/specs/platform/portfolio.json` |
| Structural validator + tests | `docs/tools/platform_portfolio/` |
| Delta specs (now living) | `openspec/specs/platform-subproject-governance/`, `openspec/specs/platform-portfolio-documentation-integrity/` |
| Process record (proposal, design, exploration, review-ledger, delta specs) | this dated archive folder |

Numeric SP briefs, founding designs, and prior archived evidence remain byte-unchanged.

## Verification Evidence

- `python docs/tools/platform_portfolio/validate.py --root .` → `CLEAN — 0 violations`.
- `python -m unittest discover -s docs/tools/platform_portfolio -p 'test_*.py'` → 5 passed.
- Structural review: judgment-day dual-blind; finding JD-001 (manifest path provenance) fixed; loop terminated by the deterministic validator.
- Semantic review: fresh-context PASS (aliases, transfer homes, edges, decisions, taxonomy, SP-DATA-ENVIRONMENTS exclusions) — 0 blocker/critical.

## Independent Review

Merged as PR #41 after structural and semantic review. Over-engineered E/D/V
migration machinery was pruned (Decision B) as the root cause of the earlier
review→fix loop; migrating the docs tree is deferred to ordinary SDD.

## Downstream

`SP-DATA-ENVIRONMENTS` (formerly SP-2) is unblocked. Next: resolve the open
blocking decisions (DP, DT, DD, DPROV-*) and specify the cross-cutting
prerequisite capabilities (Wave 1) before opening SP delivery.
