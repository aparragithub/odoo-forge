# Delta for Platform Portfolio Documentation Integrity

## MODIFIED Requirements

### Requirement: Disjoint Graphs and Atomic Transfers

`docs/specs/platform/portfolio.json` MUST remain the normative product, dependency, and evidence authority, with lineage, transitions, transfers, and dependency edges separate, resolved, concrete, and acyclic. Its `meta.live_location` MUST remain that path. Scopes MUST match `^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`; each transition has one kind and evidenced ownership. Current claims MUST have verifiable HEAD evidence; protected history, archives, and receipts MUST remain immutable. (Previously: validated graph separation and ownership.)

#### Scenario: Reject ambiguous or unsupported claims
- GIVEN graph cross-use, invalid scope, source-inconsistent ownership, or an unsupported current claim
- WHEN validation runs
- THEN validation MUST fail and identify the claim or structural violation

### Requirement: Deterministic Structural Validation

The validator at `docs/tools/platform_portfolio/validate.py` MUST deterministically check identity, references, scopes, acyclicity, aliases, evidence, gaps, and SDD decompositions in `docs/specs/platform/portfolio.json`. It MUST also run stale-claim, stabilization-roadmap/inventory-contract, and derived-artifact checks; gating MUST NOT rely on reviewer sampling. (Previously: deterministic validation covered structure and forecasts.)

#### Scenario: Reject unresolved or stale structure
- GIVEN a duplicate, unresolved reference, cyclic edge, stale claim, incorrect active inventory, or nondeterministic derived output
- WHEN the validation suite runs
- THEN it MUST exit non-zero and name the violation

### Requirement: Portfolio Scope, Not Migration Project

`docs/specs/platform/portfolio.json` MUST describe portfolio outcomes, capabilities, ports, adapters, integrations, workflows, decisions, evidence, and traceability. It MUST NOT embed migration machinery. Active OpenSpec inventory truth MUST be owned by the stabilization roadmap/inventory validation contract, which MUST identify this change and blocked `sp-data-environments`; `CHG-FIRST-DATABASE-ADAPTER` MUST be archived as superseded with a pointer to its implementation. `S62` references MUST be removed when unverifiable, never fabricated. (Previously: prohibited migration machinery and kept SP-DATA-ENVIRONMENTS blocked.)

#### Scenario: Preserve truthful active inventory
- GIVEN the roadmap/inventory contract contains this change, blocked `sp-data-environments`, and a superseded adapter change
- WHEN inventory reconciliation and archival run
- THEN the adapter change MUST be absent from active work and traceable through its pointer

#### Scenario: Remove unverifiable S62 claims
- GIVEN an S62 reference has no evidence
- WHEN current guidance is reconciled
- THEN the reference MUST be removed and the gap reported

## ADDED Requirements

### Requirement: Authority and Derived Artifact Ownership

Each artifact MUST be classified as authoritative, derived, or historical/protected. SVG MUST be produced from Mermaid by the renderer; HTML MUST be updated only after ownership and source are verified. Spanish guide language MUST be preserved, and generated output MUST match its source. Protected archives, receipts, and dated documents MUST NOT be edited.

#### Scenario: Verify source before update
- GIVEN an architecture HTML file has an unverified or generated ownership chain
- WHEN an update is requested
- THEN the update MUST stop until the authoritative source is verified

#### Scenario: Preserve language and derivation
- GIVEN Mermaid and the Spanish implementation guide are current
- WHEN the implementation diagram family is regenerated
- THEN SVG MUST derive from Mermaid and the guide's Spanish content MUST remain intact

### Requirement: Evidence-Backed Current Guidance

Roadmap, README, portfolio, guide, Mermaid, SVG, and HTML claims MUST resolve to current evidence or an explicit gap. The system MUST NOT rewrite historical evidence to make a claim pass.

#### Scenario: Accept supported current claims
- GIVEN a claim resolves to HEAD evidence and its source ownership is valid
- WHEN stale-claim validation runs
- THEN the claim MUST pass without changing protected history

### Requirement: Chained Delivery Scope

The change MUST be delivered as separate, independently verifiable slices, each with authored additions plus deletions no greater than 400 lines: inventory/portfolio/roadmap; README/guide/Mermaid; and generated SVG/HTML plus validation receipts. Unit 4 registry, Git, and workspace runtime-risk recheck MUST remain a separate later scope.

#### Scenario: Reject oversized or cross-scope slice
- GIVEN a slice exceeds 400 authored changed lines or includes Unit 4 runtime-risk work
- WHEN delivery planning is validated
- THEN the plan MUST be rejected until split or deferred
