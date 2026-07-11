# Platform Subproject Governance Specification

**Artifact parity ID:** `SPEC-PORTFOLIO-GOVERNANCE-V5`

## Requirements

### Requirement: Normative Planning Authority

`portfolio-plan.json` MUST be the normative planning authority and exhaustively enumerate `meta`, `items`, `decisions`, `transitions`, `transfers`, `edges`, and `decompositions` (future SDD changes). Grouped narrative is non-normative. Any docs-tree metadata mirror becomes authoritative only through ordinary SDD migration, not through embedded slice ceremony.

#### Scenario: Reject narrative reconstruction
- GIVEN a consumer infers planning records from narrative prose
- WHEN planning data is loaded
- THEN it MUST reject that reconstruction and read `portfolio-plan.json`

### Requirement: Oversized Hybrid Artifact Parity

When a machine-readable artifact exceeds an Engram observation limit, hybrid persistence MUST use ordered raw UTF-8 chunks of at most 40,000 characters. Chunk content MUST be unchanged and wrapper-free. The parent topic MUST contain a versioned manifest with encoding, ordered chunk topics, per-chunk character/byte counts and SHA-256, total counts and SHA-256, an exact-concatenation rule, and superseded representations. Reconstructed Engram bytes MUST equal the filesystem artifact.

#### Scenario: Reconstruct oversized planning data
- GIVEN the manifest and every listed raw chunk
- WHEN chunk content is concatenated exactly in manifest order and encoded as UTF-8
- THEN its bytes and SHA-256 MUST equal `portfolio-plan.json`

### Requirement: Taxonomy and Evidence

Item kind MUST be `sp|prerequisite|port|adapter|integration|workflow|sdd_change`. Every item MUST carry identity, title, owner, lifecycle status, evidence date, acceptance objects with evidence/gaps, decision IDs, and lineage arrays. References MUST resolve. Every historical `SP-1`…`SP-10` reference MUST resolve through the `historical_alias_map`, and every renamed or split item MUST carry its `historical_aliases`. Decomposition `acceptance_ids` MUST resolve against item acceptance objects. Every reference in the plan MUST resolve under the deterministic validator.

Decisions MUST be separate records. `#6375` is decided evidence; provider selection, tenancy/access, data policy, onboarding, remote target/DNS/TLS, prerequisite grouping, and provider choices remain unresolved blockers.

`proposed` requires a gap and no delivery claim; `validated` requires approved contracts; `active` requires a complete open decomposition; `partially delivered` requires evidence plus a gap; `achieved` requires every acceptance satisfied; `superseded` requires retained evidence and successors. Local evidence MUST resolve; external HTTPS evidence receives syntax checks only.

#### Scenario: Reject incomplete or false authority
- GIVEN a record, reference, acceptance, decision, or status lacks required evidence
- WHEN validation runs
- THEN validation MUST fail
