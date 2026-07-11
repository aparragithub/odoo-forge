# Proposal: Platform Database Provider Core

## Intent

Establish SP-2's stable lifecycle foundation for three dependent child changes.

## Scope

### In Scope
- Define runtime-checkable `DatabaseProvider` with exact canonical signatures: `provision(spec: DatabaseSpec) -> DatabaseRef`, `clone(source_ref: DatabaseRef, target_spec: DatabaseSpec) -> DatabaseRef`, `randomize(source_ref: DatabaseRef, target_spec: DatabaseSpec, rules: AnonymizationRules) -> DatabaseRef`, and `drop(ref: DatabaseRef) -> None`.
- Add immutable database specs, refs, lineage, anonymization-rule inputs, and typed lifecycle errors.
- Add creator-owned `CreationReceipt`/`CreatedDatabase` outcomes and capture-compatible `DatabaseCaptureRef` artifact types; copy coordination remains elsewhere.
- Deliver `odoo_forge_postgres_docker` for all four operations with explicit import boundaries.
- Cover runtime/signature conformance, core invariants, and Docker lifecycle integration.

### Out of Scope
- Backend runtime routing or PostgreSQL ownership extraction.
- Destination policy, authorization, audit, or persistence.
- Filestore coordination, capture orchestration, copy CLI, or umbrella integration acceptance.

## Capabilities

### New Capabilities
- `database-provider-core`: Canonical contracts, lifecycle values, receipts, typed failures, and the Docker PostgreSQL adapter.

### Modified Capabilities
- None.

During umbrella reconciliation, the parent `database-provider-lifecycle` provider-contract and Docker-lifecycle requirements will delegate to this capability; the parent retains cross-child acceptance without duplicating requirements.

## Approach

Land an additive forced PR chain, each below 400 changed lines with its tests: (1) contracts/models/errors/conformance, (2) provision/drop, (3) clone/randomize plus receipt/artifact compatibility, (4) packaging and adapter integration. Keep current Slice 4b backend routing untouched.

## Handoff Contracts

- Runtime integration consumes `DatabaseSpec`, `DatabaseRef`, `CreatedDatabase`, receipts, and lifecycle errors.
- Data governance consumes immutable refs, lineage, operation/receipt identity, and typed outcomes.
- Coordinated copy consumes `DatabaseCaptureRef`, `DatabaseCreationProvider`/`CreatedDatabase`, and created-only drop semantics.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/{database,ports}/` | New | Pure contracts and values |
| `src/odoo_forge_postgres_docker/` | New | Docker PostgreSQL adapter |
| `pyproject.toml` | Modified | Package and forbidden import contract |
| `tests/{database,ports,adapters}/` | New | Core, conformance, integration coverage |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Canonical signatures drift | Med | `inspect.signature` plus runtime conformance |
| Existing resources are deleted | Med | Creator receipts; drop only `created=True` resources |
| Temporary dual ownership | Med | Additive adapter only; routing stays with Slice 4b |

## Rollback Plan

Revert the additive core/adapter/package slices. Slice 4b remains the active PostgreSQL owner; integration cleanup removes only receipt-owned resources.

## Dependencies and Relationship

- Depends only on completed Slice 4b.
- First child of the approved four-child `platform-database-provider` SP-2 umbrella; sole owner of its provider-contract and Docker-lifecycle requirements.

## Success Criteria

- [ ] Runtime and exact-signature conformance pass.
- [ ] Immutable lineage/receipt/error invariants pass.
- [ ] Docker provision/clone/randomize/drop round-trips and created-only cleanup pass.
- [ ] Import-linter, typing, build, and every sub-400-line PR gate pass.
