# Docker PostgreSQL Database Adapter Specification

## Purpose

Define the additive, isolated Docker PostgreSQL implementation of the accepted `DatabaseProvider` lifecycle without changing provider-neutral contracts, local-backend ownership, or runtime routing.

## Requirements

### Requirement: Isolated Docker Lifecycle

The adapter MUST implement the accepted database lifecycle for Docker PostgreSQL and MUST be selectable only through `DPROV-DB`. It MUST remain additive and MUST NOT extract, reroute, or cut over the local-backend PostgreSQL. Provider-neutral contracts, opaque handoffs, typed redaction, and exclusions for tracker integration, control-plane authority, data environments, data copy, and PublishedLayer/Override semantics MUST remain unchanged.

#### Scenario: Provider is selected without cutover

- GIVEN `DPROV-DB` selects the Docker PostgreSQL provider
- WHEN a database lifecycle operation is requested
- THEN the adapter handles the operation through the accepted provider contract
- AND local-backend runtime routing remains unchanged

#### Scenario: Unsupported adjacent scope is not absorbed

- GIVEN a request concerns data copy, control-plane authority, data environments, or PublishedLayer/Override semantics
- WHEN the adapter boundary is evaluated
- THEN the request remains outside this capability

### Requirement: Ownership-Scoped Resource Lifecycle

The adapter MUST record durable authority for resources it creates and MUST mutate, reconcile, recover, disable, delete, or clean up only resources proven by that authority to belong to its creation lineage. Labels and inspection data are discovery identifiers only; adopted, legacy, external, and unproven resources MUST remain protected and MUST be recreated when required.

#### Scenario: Created resources are reconciled and cleaned

- GIVEN the adapter created Docker resources and durable authority verifies their lineage
- WHEN reconciliation, rollback, or cleanup runs after restart
- THEN only authority-owned resources are considered
- AND successful cleanup leaves no adapter-owned residuals

#### Scenario: Foreign or legacy resource is protected

- GIVEN a resource is external, adopted, legacy, or lacks matching authority
- WHEN destructive recovery or cleanup is requested
- THEN the adapter refuses it and reports a typed, redacted ownership outcome

### Requirement: Credential and Artifact Handoffs Remain Opaque

The adapter MUST obtain credentials only through `CAP-CREDENTIALS`, inject them through an approved Docker target-side mechanism, and keep them opaque outside that step. Backup outputs and restore inputs MUST use `CAP-DATA-ARTIFACTS` references; the adapter MUST validate restore readiness before mutation.

#### Scenario: Provision and restore use approved handoffs

- GIVEN a valid `CredentialHandle` and, for restore, a valid `DataArtifactRef`
- WHEN provisioning or restore is requested
- THEN the adapter completes using those references
- AND returned values, diagnostics, evidence, and Docker inspection expose neither credentials nor artifact bytes

#### Scenario: Invalid restore input fails closed

- GIVEN a restore reference is unavailable, incoherent, or fails integrity validation
- WHEN restore readiness is checked
- THEN the operation fails before target mutation and the failure is typed and redacted

### Requirement: Bounded Availability and Recovery

The adapter MUST provide bounded availability evidence after provisioning or recovery and MUST report unavailable or failed operations without leaking secrets or artifact details. Rollback MUST compensate only adapter-owned mutations.

#### Scenario: Docker lifecycle reaches bounded availability

- GIVEN Docker prerequisites are available and provisioning succeeds
- WHEN bounded readiness is evaluated
- THEN the database becomes available within the defined bound
- AND the evidence identifies the operation without sensitive values

#### Scenario: Failed mutation rolls back safely

- GIVEN a provisioning or recovery mutation fails after creating some resources
- WHEN rollback is requested
- THEN only resources created by that operation are compensated
- AND unrelated or external resources remain unchanged

### Requirement: Real-Docker Acceptance Evidence

The capability MUST provide real-Docker evidence covering provisioning, bounded availability, recovery, rollback, credential and artifact redaction, and ownership-safe cleanup. Evidence MUST demonstrate no runtime cutover and no provider-neutral contract redefinition.

#### Scenario: Complete evidence supports acceptance

- GIVEN real-Docker evidence covers every required lifecycle and boundary
- WHEN capability acceptance is evaluated
- THEN the adapter may be accepted as the first Docker PostgreSQL provider

#### Scenario: Incomplete or simulated evidence blocks acceptance

- GIVEN any required real-Docker or ownership-safety evidence is missing
- WHEN acceptance is evaluated
- THEN the capability remains unaccepted

### Requirement: Credential Cleanup Residuals Are Rollback-Incomplete

When cleanup of an opaque `credential-file` target leaves a residual, the adapter MUST produce the existing `RollbackIncompleteError` outcome even when container rollback succeeds. The outcome MUST preserve the rollback receipt, causal failure, and resource residuals, and MUST expose only the safe `credential-file` identifier. Paths, secrets, handles, descriptors, and equivalent sensitive material MUST NOT be observable in the error, receipt, diagnostics, or reports.

#### Scenario: Credential-file residual survives successful container rollback

- GIVEN provisioning fails and cleanup cannot remove the credential target
- WHEN all receipt-owned container rollback operations otherwise succeed
- THEN the adapter raises `RollbackIncompleteError`
- AND the outcome preserves the receipt and original failure cause with residual `credential-file`

#### Scenario: Cleanup diagnostics remain redacted

- GIVEN a credential target contains a secret and its cleanup fails
- WHEN the rollback-incomplete outcome is observed
- THEN only the opaque `credential-file` token is exposed
- AND neither the target path nor secret is observable

### Requirement: Runtime Evidence Must Prove Fail-Closed Acceptance

Acceptance MUST remain false unless final-lineage real-Docker, authority, and ownership-safety evidence is genuine at runtime. Missing, simulated, imported, forged, stale, or inspection-reconstructed evidence MUST NOT support acceptance.

#### Scenario: Missing or stale evidence blocks acceptance

- GIVEN required final-lineage or authority evidence is missing or stale
- WHEN acceptance readiness is evaluated
- THEN acceptance remains false and the blocking condition is reported

#### Scenario: Simulated or forged evidence blocks acceptance

- GIVEN evidence is simulated, imported, or reconstructed from inspection
- WHEN acceptance readiness is evaluated
- THEN acceptance remains false and the runtime test demonstrates fail-closed behavior
