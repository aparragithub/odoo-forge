# Platform Portfolio Documentation Integrity Specification

**Artifact parity ID:** `SPEC-PORTFOLIO-INTEGRITY-V5`

## Requirements

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

### Requirement: Canonical Apply and Quality Acceptance
The canonical parent apply status MUST be `Apply Complete — Ready for sdd-verify`; parent SDD verification against the parent artifact MUST enforce it. The child documentation validator MUST NOT enforce foreign parent OpenSpec paths in its staged binding and MUST require Ruff check/format.

#### Scenario: Child staged independence
- GIVEN the child staged target excludes foreign parent OpenSpec paths
- WHEN child validation runs
- THEN validation MUST evaluate its own staged candidate and pass

#### Scenario: Reject quality drift
- GIVEN either validator file fails Ruff
- WHEN the quality gate runs
- THEN verification MUST fail with Ruff

#### Scenario: Reject parent status
- GIVEN the combined parent has a noncanonical status
- WHEN parent SDD verification runs
- THEN verification MUST fail

### Requirement: Deterministic Derived Artifact Verification
The validator MUST enforce fixed-renderer `--check` byte coherence through an injectable seam; stale SVG MUST fail.

#### Scenario: Reject changed rendered bytes
- GIVEN regenerated SVG differs from committed bytes
- WHEN validation runs
- THEN validation MUST fail

#### Scenario: Deterministic tests
- GIVEN tests inject deterministic renderer results
- WHEN tests run
- THEN tests MUST repeat without Docker

### Requirement: Complete Child Staged Target
The child staged review target MUST include every non-OpenSpec runtime/documentation dependency it validates: current Mermaid, generated SVG, validator, tests, HTML, and child artifacts.

#### Scenario: Reject incomplete staged target
- GIVEN current Mermaid or generated SVG is absent from the child staged target
- WHEN child review runs
- THEN review MUST fail

#### Scenario: Reject stale diagram claims
- GIVEN combined binding contains stale diagram claims
- WHEN parent SDD verification runs
- THEN verification MUST fail

### Requirement: Exact Current Guide Link
HTML MUST contain the exact repository-contained current-guide target; alternative, external, absolute, traversal, or merely resolvable links MUST fail.

#### Scenario: Require canonical target
- GIVEN HTML contains an alternative or escaping link
- WHEN validation runs
- THEN validation MUST fail

### Requirement: S62 Removal and Gap Reporting
Valid archived S62 MUST remain accepted unchanged. Any unverifiable reference, including an S62 fixture, MUST be removed from active claims and represented by matching `gap_catalog`; fabricated replacement MUST fail. No portfolio gap/change is required for valid S62.

#### Scenario: Retain valid S62
- GIVEN S62 resolves to archived evidence
- WHEN validation runs
- THEN S62 MUST remain accepted unchanged

#### Scenario: Remove unverifiable evidence
- GIVEN an unverifiable reference has a matching gap entry
- WHEN validation runs
- THEN the reference MUST be absent and the gap reported

#### Scenario: Reject fabricated replacement
- GIVEN an unverifiable reference has unsupported replacement or no matching gap
- WHEN validation runs
- THEN validation MUST fail

### Requirement: Verified HTML Ownership and Scope
HTML updates MUST include validated hand-authored ownership and current/target metadata; absent or unverified ownership MUST refuse updates.

#### Scenario: Refuse unverified ownership
- GIVEN HTML ownership is missing or unverified
- WHEN updating
- THEN validation MUST fail

### Requirement: Native Staged Scope Authority
The native staged review target/receipt plus SDD verification MUST enforce scope, Unit4 exclusion, and >400 high-tier approval; the repository validator MUST NOT claim that authority.

#### Scenario: Keep repository planning helpers non-authoritative
- GIVEN slice helpers receive scope or budget text
- WHEN validation runs
- THEN they MUST NOT gate validation

### Requirement: Immutable Parent Failure Evidence
The child MUST preserve `evidence/parent-verify-fail.md` and `.sha256` immutably at SHA-256 `0fbb60e3b0aba12a46cc26a69c57b40ffb26fa1c60adde5946c0ee9018d084c4`; parent SDD verification with native review binding exclusively validates an advanced canonical PASS report.

#### Scenario: Preserve failure
- GIVEN snapshot/hash match before reverification
- WHEN evidence validation runs
- THEN live `verify-report.md` MAY match it as historical input

#### Scenario: Authorize PASS advancement
- GIVEN child PASS and new combined lineage/binding/evidence revision are approved
- WHEN reverification writes a canonical PASS envelope for the combined candidate
- THEN advancement MUST pass and the snapshot remain unchanged

#### Scenario: Reject drift
- GIVEN premature report drift, missing authority, FAIL/unknown verdict, or snapshot/receipt mutation
- WHEN evidence validation runs
- THEN validation MUST fail

#### Scenario: Reject staged/worktree mismatch
- GIVEN a dirty worktree passes but staged candidate evidence differs
- WHEN review or verification runs
- THEN success MUST NOT be accepted

### Requirement: Ordered Child and Parent Closure
The lifecycle MUST be child implementation, review, verification, incorporation, combined review/bind, and reverification in order. Reverification MUST NOT pass before binding approval.

#### Scenario: Enforce closure order
- GIVEN child verification succeeds without new combined binding
- WHEN parent verification runs
- THEN verification MUST be blocked

#### Scenario: Complete closure
- GIVEN child PASS and a new combined lineage is approved/bound
- WHEN parent reverification runs
- THEN it MUST evaluate the combined candidate
