# Archive Report: CAP-RESOURCE-OWNERSHIP

**Archive Date**: 2026-07-19
**Change Name**: CAP-RESOURCE-OWNERSHIP
**Artifact Store**: openspec
**Branch**: cap-resource-ownership
**Verification Verdict**: PASS (re-verified after CRITICAL fix)

## Executive Summary

`CAP-RESOURCE-OWNERSHIP` has been successfully archived after implementation, verification, and remediation of one CRITICAL issue. The delta spec has been merged into main specs at `openspec/specs/resource-ownership/spec.md`. The change folder has been moved from `openspec/changes/CAP-RESOURCE-OWNERSHIP/` to `openspec/changes/archive/2026-07-19-CAP-RESOURCE-OWNERSHIP/`. All 18 tasks are complete with evidence. The readiness gate `AC-CAP-RESOURCE-OWNERSHIP-READY` is now marked `achieved` with accurate supporting evidence (8/8 requirements, 16/16 scenarios compliant).

## Contract-First Outcome

This change defines one normative, provider-neutral platform contract for resource ownership:

- **Ownership State Model**: Exactly three states (`created`, `adopted`, `external`), generalized from the existing database-scoped `ResourceOwnership` enum to arbitrary resource kinds without introducing new states in v1.
- **Ownership Receipt / Evidence Shape**: Composed of an opaque operation proof, owned resource ids, and a live-proof expectation — generalized from `CreationReceipt` but free of Docker-label specifics.
- **Tenant Attribution Composition**: Optional tenant linkage composed with (not replacing) ownership state; `external` and pre-tenancy resources may remain tenant-unattributed until adopted.
- **Durable-Operation Composition**: Receipt operation identity reuses `CAP-DURABLE-OPERATIONS`' `DurableOperationIdentity{operation_id, request_digest}` rather than duplicating a parallel model.
- **`PORT-RESOURCE-OWNERSHIP` Read/Attest Surface**: v1 exposes read-only semantics (`describe_ownership` + `attest_ownership`); transition verbs are deferred to `SP-CONTROL-PLANE-AUTHORITY`.

## Move-and-Re-Export Design Decision

The design chose a **move-and-re-export** pattern for the canonical ownership vocabulary:

- The generalized types (`ResourceOwnership`, `ResourceRef`, `OwnershipReceipt`, `OwnershipRecord`, `OwnershipAttestation`, `TenantAttribution`, relocated `OperationIdentity`, `CreationReceipt`) relocate to a new core package `src/odoo_forge/resource_ownership/types.py`.
- The existing `src/odoo_forge/database/types.py` becomes a re-export shim, preserving all 28+ existing callers' import paths unchanged and maintaining backward compatibility.
- The dependency arrow now correctly flows `database → resource_ownership` (specific → general), adhering to hexagonal architecture.
- The shim's `__all__` remains byte-identical to its pre-change value, with zero new symbols exposed.

This design avoids scope bleed into database-domain concerns and keeps the ownership contract provider-neutral and resource-kind-agnostic.

## Critical Issue Found and Fixed

### Initial Problem (sdd-verify FAIL)

The initial apply-phase implementation typed `OwnershipReceipt.operation` as the legacy `OperationIdentity{value: str}` (a Docker-token type) rather than composing with `CAP-DURABLE-OPERATIONS`' real stable identity. This violated the spec requirement "Operation Identity Composes With CAP-DURABLE-OPERATIONS Without Duplication" — a parallel operation-identity model, not reuse. Both spec scenarios for this requirement remained untested and failing.

### Fix Applied (TDD Cycle)

**RED**: Added two new tests:
- `test_ownership_receipt_reuses_durable_operation_identity`: Constructs a `DurableOperationIdentity`, builds an `OwnershipReceipt` with it, asserts `receipt.operation is identity`, and exercises `DurableOperationIdentity.matches_request_digest()` through the receipt.
- `test_ownership_receipt_rejects_a_parallel_operation_identity_model`: Asserts `pydantic.ValidationError` is raised when legacy `OperationIdentity` is passed where `DurableOperationIdentity` is expected.

**GREEN**: Changed `OwnershipReceipt.operation: OperationIdentity` → `OwnershipReceipt.operation: DurableOperationIdentity` (imported from `odoo_forge.durable_operations.types`) in `src/odoo_forge/resource_ownership/types.py`. Updated `_receipt()` helpers in both test files to build `DurableOperationIdentity` instances.

**REFACTOR**: Wrapped the deliberate-mismatch test in `cast(Any, ...)` with an explanatory comment to satisfy mypy strict (the test proves runtime rejection of a case the type checker already forbids statically).

### Re-Verification Results

- Full suite: 764 passed (was 762, +2 new tests, 0 broken)
- mypy strict: 129 files, 0 errors
- ruff: All checks passed
- lint-imports: 6/6 contracts kept, no cycle (new `resource_ownership → durable_operations` core-to-core edge is permitted)
- Docker adapter: Zero-diff (unchanged)
- Shim integrity: `database/types.py::__all__` byte-identical
- Portfolio.json: `AC-CAP-RESOURCE-OWNERSHIP-READY = achieved / gaps: []` claim is now accurate and truthful

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| resource-ownership | **Created new main spec** | Delta spec from `openspec/changes/CAP-RESOURCE-OWNERSHIP/specs/resource-ownership-contract/spec.md` is now the authoritative main spec at `openspec/specs/resource-ownership/spec.md`. The spec is unchanged from the delta (no prior resource-ownership spec existed). Contains 8 requirements, 16 scenarios, and one readiness acceptance gate `AC-CAP-RESOURCE-OWNERSHIP-READY`. |

## Archive Contents

- **proposal.md** ✅ — Intent, scope, affected areas, risks, rollback plan, dependencies, success criteria
- **exploration.md** ✅ — Current state, affected areas, approaches, recommendations, ready-for-proposal assessment
- **design.md** ✅ — Technical approach, architecture decisions, conceptual model, interfaces, testing strategy, migration plan
- **specs/resource-ownership-contract/spec.md** ✅ — Authoritative contract spec (8 requirements, 16 scenarios)
- **tasks.md** ✅ — 5 task groups, 18 total tasks, all checked (3 slices + final validation + remediation)
- **apply-progress.md** ✅ — Original 3-slice TDD history + remediation cycle (RED→GREEN→REFACTOR evidence)
- **verify-report.md** ✅ — Re-verify PASS verdict after CRITICAL fix; full compliance matrix (8/8 requirements, 16/16 scenarios); 764/764 tests passing; zero regression

## Source of Truth Updated

The following spec is now the authoritative single source of truth for resource ownership contracts across the platform:

- **`openspec/specs/resource-ownership/spec.md`** — normative, provider-neutral contract defining ownership state, receipt/evidence shape, tenant attribution, operation-identity composition, and the `PORT-RESOURCE-OWNERSHIP` read/attest surface.

Downstream capabilities (`SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, `WF-DATA-COPY`) MUST consume this spec and MUST NOT redefine ownership states, the receipt shape, or tenant-attribution composition.

## Engram Artifacts for Traceability

All SDD artifacts are persisted in Engram for this change:

- Observation #9635: `sdd/CAP-RESOURCE-OWNERSHIP/proposal`
- Observation #9640: `sdd/CAP-RESOURCE-OWNERSHIP/spec`
- Observation #9641: `sdd/CAP-RESOURCE-OWNERSHIP/design`
- Observation #9646: `sdd/CAP-RESOURCE-OWNERSHIP/tasks`
- Observation #9655: `sdd/CAP-RESOURCE-OWNERSHIP/verify-report` (re-verify PASS after CRITICAL fix)
- This archive report: `sdd/CAP-RESOURCE-OWNERSHIP/archive-report` (new)

## Portfolio.json Status

**Not modified** — the apply phase already updated `docs/specs/platform/portfolio.json` to:
- Set `CAP-RESOURCE-OWNERSHIP` status to `achieved`
- Set `AC-CAP-RESOURCE-OWNERSHIP-READY` status to `achieved` with `evidence=[S63, S64, S65, S66, S67]`
- Clear `gaps: []` (no remaining evidence gaps)

The re-verify pass confirmed these claims are now accurate and truthful: every requirement scenario is genuinely satisfied by passing tests or verifiable static evidence.

## SDD Cycle Complete

This change has been fully planned (proposal + exploration), specified (delta spec merged to main specs), designed (contract-first approach with move-and-re-export), implemented (3 slices + remediation), verified (PASS after CRITICAL fix), and archived.

The readiness gate `AC-CAP-RESOURCE-OWNERSHIP-READY` unblocks four downstream hard-edge capabilities to proceed to their own spec/design phases:
- `SP-CONTROL-PLANE-AUTHORITY` — may now define runtime ownership authority
- `SP-RESOURCE-LIFECYCLE` — may now define lifecycle/retention policies
- `WF-ENVIRONMENT-REQUEST` — may now define environment request workflows
- `WF-DATA-COPY` — may now define coordinated data-copy workflows

All downstream consumers MUST consume this contract as their ownership vocabulary source and MUST NOT redefine ownership semantics.
