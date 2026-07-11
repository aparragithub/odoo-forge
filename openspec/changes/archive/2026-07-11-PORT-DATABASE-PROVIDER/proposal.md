# Proposal: Re-baseline the Database Provider Port

## Intent

Define the provider-neutral `DatabaseProvider` contract transferred by `X7`, closing gap `G3` with evidence for `AC-PORT-DATABASE-PROVIDER-READY` without reviving superseded SP-2 scope.

## Scope

### In Scope
- Provider operations, immutable values, credential/artifact references, lifecycle ownership, typed failures, conformance, and gate evidence.

### Out of Scope
- Docker PostgreSQL; credential materialization; data-artifact implementation; runtime cutover.
- Destination policy, coordinated copy, CLI workflow, or managed-data-environment outcomes.

## Capabilities

### New Capabilities
- `database-provider`: Provider-neutral database lifecycle port, values, ownership safety, failures, and conformance contract.

### Modified Capabilities
- None.

## Approach

Specify a runtime-checkable port with exact signatures for `provision`, `restore`, `adopt`, `reconcile`, `delete`, and `cleanup`. `provision` and artifact-backed `restore` return immutable `DatabaseCreation` values containing `DatabaseRef` and `CreationReceipt`; `adopt` grants no deletion authority; `reconcile` recovers mutation-before-return; `delete` requires creator proof; `cleanup` compensates only receipt-owned resources and reports every residual failure.

Provider-owned values are `DatabaseSpec`, `DatabaseRef`, `DatabaseCreation`, `CreationReceipt`, `ResourceOwnership` (`created`, `adopted`, `external`), `CleanupReport`, and operation identity. Inputs use opaque `CredentialHandle` and `DataArtifactRef` contracts owned elsewhere; provider values contain no secrets or data bytes.

Typed failures cover invalid requests, unavailable credentials/artifacts/resources, conflicts, readiness, ownership refusal, operation failure, and incomplete cleanup; all are redacted.

| Draft concept retained | Current justification |
|---|---|
| Protocol plus exact-signature checks | `X7` assigns the provider contract; repository ports already require structural and signature conformance. |
| Immutable refs, typed failures | Required provider-owned handoff without adapter detail. |
| Receipts, reconciliation, guarded cleanup | Makes creation/adoption/deletion ownership safe and testable. |
| Opaque credential/artifact references | `G15`/`G16` keep those implementations parallel to this port. |

Archived clone/randomize APIs and artifact/credential implementations are not retained.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `openspec/specs/database-provider/` | New | Canonical capability after archive |
| `src/odoo_forge/{ports,database}/` | Future | Contract and provider-owned values only |
| `tests/{ports,database}/` | Future | Conformance and invariant evidence |
| `docs/specs/platform/portfolio.json` | Future | Gate evidence/status recording |

## Risks

Provider-specific leakage or unsafe deletion is mitigated by opaque dependencies, ownership proof, and negative conformance scenarios.

## Rollback Plan

Withdraw this draft; leave the gate `proposed`, gap `G3` open, and downstream `G17` blocked. No runtime rollback exists.

## Dependencies

None for the port. Referenced credential/artifact contracts remain independently owned parallel adapter inputs.

## Success Criteria

- [ ] Specs define every operation, value invariant, ownership transition, and typed failure.
- [ ] Conformance evidence covers runtime shape, exact signatures, redaction, and safe cleanup.
- [ ] `AC-PORT-DATABASE-PROVIDER-READY` records approved proposal/spec/design plus verification receipt IDs, clears `G3`, and advances only after evidence acceptance.
- [ ] Force-chained delivery keeps each future authored slice within 400 changed lines.
