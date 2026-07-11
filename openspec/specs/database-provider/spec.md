# Database Provider Specification

## Purpose

Define the provider-neutral database lifecycle boundary required to satisfy `AC-PORT-DATABASE-PROVIDER-READY` without selecting an infrastructure provider or implementing adjacent capabilities.

## Requirements

### Requirement: Provider Lifecycle Interface

The system MUST expose a runtime-checkable `DatabaseProvider` contract with these exact signatures: `provision(DatabaseSpec, CredentialHandle) -> DatabaseCreation`; `restore(DatabaseSpec, DataArtifactRef, CredentialHandle) -> DatabaseCreation`; `adopt(DatabaseRef) -> DatabaseRef`; `reconcile(OperationIdentity) -> DatabaseCreation`; `delete(DatabaseCreation) -> None`; and `cleanup(CreationReceipt) -> CleanupReport`. Credential and artifact inputs SHALL remain opaque references.

#### Scenario: Lifecycle surface conforms

- GIVEN a candidate database provider
- WHEN its runtime shape and operation signatures are inspected
- THEN it exposes exactly the six lifecycle operations with the contract signatures
- AND it passes structural conformance without importing an adapter

#### Scenario: Unsupported lifecycle surface is rejected

- GIVEN a candidate missing an operation or using an incompatible signature
- WHEN conformance is evaluated
- THEN conformance fails before the candidate is accepted

### Requirement: Immutable Provider Values

The system MUST define immutable provider-owned `DatabaseSpec`, `DatabaseRef`, `DatabaseCreation`, `CreationReceipt`, `ResourceOwnership`, `CleanupReport`, and operation identity values. `DatabaseCreation` SHALL contain a `DatabaseRef` and `CreationReceipt`; provider values MUST NOT contain credential secrets or artifact data bytes.

#### Scenario: Creation returns an immutable handoff

- GIVEN a valid provision or artifact-backed restore request
- WHEN the provider reports success
- THEN it returns a `DatabaseCreation` with a reference and creation receipt
- AND consumers cannot mutate the returned values

#### Scenario: Secret-bearing value is invalid

- GIVEN a proposed provider value containing credential material or artifact bytes
- WHEN value invariants are validated
- THEN validation fails without exposing the sensitive content

### Requirement: Ownership-Safe Lifecycle

The system MUST classify resources as `created`, `adopted`, or `external`. `adopt` MUST NOT grant deletion authority. `delete` MUST require creator proof, `cleanup` MUST compensate only resources owned by its receipt, and `reconcile` MUST recover an operation whose mutation occurred before a result was returned.

#### Scenario: Receipt-owned creation is deleted

- GIVEN a created resource and matching creator proof
- WHEN deletion is requested
- THEN the provider may delete that resource
- AND no unrelated resource is affected

#### Scenario: Adopted resource deletion is refused

- GIVEN an adopted or external resource without creator proof
- WHEN delete or cleanup is requested
- THEN the provider refuses destructive action
- AND reports the ownership reason

### Requirement: Typed, Redacted Outcomes

The system MUST report invalid requests, unavailable credentials, artifacts or resources, conflicts, readiness failures, ownership refusal, operation failures, and incomplete cleanup as typed, redacted failures. `CleanupReport` MUST identify every residual cleanup failure without secret or artifact-data disclosure.

#### Scenario: Cleanup has residual failures

- GIVEN receipt-owned cleanup where one compensation fails
- WHEN cleanup completes
- THEN its report identifies the residual failure
- AND the failure is typed and redacted

### Requirement: Port Readiness Evidence

The system MUST provide conformance evidence for runtime shape, exact signatures, immutable-value invariants, failure redaction, and ownership-safe cleanup. `AC-PORT-DATABASE-PROVIDER-READY` SHALL advance only when approved proposal, specification, design, and verification receipt identifiers are recorded, clearing `G3`.

#### Scenario: Complete evidence advances the gate

- GIVEN all required approvals and verification receipt identifiers
- WHEN readiness evidence is recorded
- THEN the gate may advance and `G3` is cleared

#### Scenario: Incomplete evidence preserves the gate

- GIVEN any required approval or receipt identifier is absent
- WHEN readiness evidence is evaluated
- THEN the gate remains unadvanced and `G3` remains open
