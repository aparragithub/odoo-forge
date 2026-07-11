# Design: Redefine Platform Subprojects Around Outcomes

**Artifact parity ID:** `DESIGN-PORTFOLIO-REDEFINITION-V6`

## Technical Approach

`portfolio-plan.json` is the normative, exhaustive description of the **portfolio**: outcomes, capabilities, ports, adapters, integrations, workflows, future SDD changes, decisions, and the old→new traceability (transitions, transfers, dependency edges). It is not a documentation-migration project plan. The proposal/specs/design carry intent and invariants without duplicating its enumerations. Numeric/founding documents remain byte-unchanged.

A committed pure-standard-library validator (`docs/tools/platform_portfolio/validate.py`) is the deterministic structural gate: it replaces reviewer sampling, which proved unreliable on a dense machine-readable artifact.

## Architecture Decisions

| Choice | Alternative | Rationale |
|---|---|---|
| One machine-readable companion | Grouped narrative inventories | Concrete records eliminate implementer inference while narrative stays reviewable. |
| Separate lineage, transitions, transfers, and edges | One overloaded graph | Historical identity, concern movement, atomic ownership, and dependencies stay independently checkable. |
| One dotted grammar | Combined/free-form labels | Every historical concern has one unambiguous destination. |
| Deterministic validator as the gate | LLM/manual review of the JSON | A dense formal artifact cannot be gated by sampling; two blind judges disagreed on a deterministic fact. An exhaustive checker terminates the review→fix loop. |
| Portfolio only; migrate via ordinary SDD | Embed a per-slice migration plan | The slice/manifest/forecast/activation machinery was where every defect and review cycle lived — the same over-engineering this change set out to cure. |
| Decision-blocked future changes | Invent provider choices | Preserves `#6375` while representing future delivery. |
| Raw Engram chunks plus manifest for oversized artifacts | Compression or a truncated single observation | Ordered UTF-8 chunks preserve transparent, byte-verifiable hybrid parity within Engram's observation limit. |

## Data Flow

```text
live evidence + #6375 → portfolio-plan.json → validate.py (deterministic gate)
                                  ↓
              independent review → archive → SP-2 unblocked
```

## Contracts and File Changes

The plan enumerates every item, acceptance object, decision, transition, transfer, dependency edge, and future SDD-change decomposition. Every record is concrete; grouped aliases, inferred paths, or implicit ownership are invalid, and every reference MUST resolve under the validator.

For hybrid persistence, an oversized artifact is split into ordered raw-text chunks of at most 40,000 characters. The parent Engram topic stores a versioned manifest with ordered topics, per-chunk and total character/byte counts and SHA-256 hashes, UTF-8 encoding, and exact-concatenation reconstruction. Round-trip bytes MUST equal the filesystem artifact.

| File | Action | Responsibility |
|---|---|---|
| `openspec/changes/platform-subproject-redefinition/portfolio-plan.json` | Create | Normative portfolio data. |
| `docs/tools/platform_portfolio/validate.py` | Create | Deterministic structural validator (stdlib only). |
| `docs/tools/platform_portfolio/test_validate.py`, `docs/tools/platform_portfolio/fixtures/valid.json` | Create | Validator tests and fixture (self-contained doc-tooling, outside the product test suite). |
| `proposal.md`, both delta specs, `design.md` | Modify | Narrative intent and invariants; no duplicate inventory. |
| `review-ledger.md` | Modify | Record corrective rows and gate state. |

## Testing Strategy

`validate.py` is the source of truth for structural correctness: unique ids, resolvable references, dotted-scope grammar, acyclic dependency edges, bidirectional alias-map consistency, and forecast consistency for future SDD changes. `docs/tools/platform_portfolio/test_validate.py` runs it against a minimal valid fixture and the live plan and asserts it catches dangling references, unresolved transfer destinations, and dependency cycles.

## Migration / Rollout

This change ships the portfolio and its validator. Migrating the docs tree (roadmap, semantic briefs, HTML, Mermaid) into a live `docs/specs/platform/` mirror is deferred to ordinary SDD changes undertaken when that work is scheduled — it is not pre-slotted into this plan. Rollback reverts the plan and validator; immutable history remains.

## Open Questions

All unresolved product decisions are blocking records in `portfolio-plan.json`; this design selects none.
