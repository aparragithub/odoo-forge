# Delta for platform-portfolio-documentation-integrity

## ADDED Requirements

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
