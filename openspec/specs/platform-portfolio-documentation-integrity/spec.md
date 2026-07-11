# Platform Portfolio Documentation Integrity Specification

**Artifact parity ID:** `SPEC-PORTFOLIO-INTEGRITY-V5`

## Requirements

### Requirement: Disjoint Graphs and Atomic Transfers

`portfolio-plan.json` is normative. Item lineage, concern transitions, atomic transfers, and dependency edges MUST remain separate; references MUST resolve; edges MUST be concrete and acyclic. Scopes MUST match `^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`. Each transition has one kind; each origin/scope has one evidenced destination; every transition member has matching transfer membership.

SP-9 inventory, request actions, and pipeline actions remain separate. SP-8 quota occurs exactly once at `CAP-TENANCY`. SP-2 excludes request approval and retention ownership. SP-10 uses `lifecycle.orphan-reclamation`, transfers no quota, and assigns each live concern once.

#### Scenario: Reject ambiguous semantics
- GIVEN graph cross-use, shorthand, an invalid/duplicate scope, or source-inconsistent ownership
- WHEN validation runs
- THEN validation MUST fail

### Requirement: Deterministic Structural Validation

`portfolio-plan.json` MUST pass a committed pure-standard-library validator (`docs/tools/platform_portfolio/validate.py`) that exhaustively checks: unique identity per collection; every item, transfer, edge, decomposition, decision, alias, evidence, and gap reference resolves; dotted transfer scopes match the grammar; the dependency-edge graph is acyclic; `historical_alias_map` is bidirectionally consistent with each item's `historical_aliases`; and every future SDD-change decomposition has a self-consistent changed-line forecast. Structural gating MUST rely on this deterministic validator rather than reviewer sampling.

#### Scenario: Reject unresolved or ambiguous structure
- GIVEN a duplicate id, unresolved reference, invalid scope, cyclic edge, or inconsistent alias map
- WHEN `validate.py` runs
- THEN it MUST exit non-zero and name the violation

### Requirement: Portfolio Scope, Not Migration Project

The plan MUST describe the portfolio — outcomes, capabilities, ports, adapters, integrations, workflows, future SDD changes, decisions, and old→new traceability. It MUST NOT embed a documentation-migration project plan (per-slice manifests, changed-line gates, activation ceremony); migrating the docs tree happens through ordinary SDD when undertaken. `SP-DATA-ENVIRONMENTS` (formerly SP-2) stays blocked until this change is independently reviewed and archived and its blocking decisions are resolved.

#### Scenario: Reject re-embedded migration machinery
- GIVEN the plan re-introduces per-slice manifests, forecasts, or an activation gate as normative structure
- WHEN the plan is reviewed
- THEN it MUST be rejected as scope creep
