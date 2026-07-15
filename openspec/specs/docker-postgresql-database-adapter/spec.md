# Docker PostgreSQL Database Adapter Specification

## Purpose

Define the additive, isolated Docker PostgreSQL implementation of the accepted `DatabaseProvider` lifecycle without changing provider-neutral contracts, local-backend ownership, or runtime routing.

## Requirements

### Requirement: Isolated Docker Lifecycle

The adapter MUST implement the accepted database lifecycle for Docker PostgreSQL and MUST be selectable only through `DPROV-DB`. It MUST remain additive and MUST NOT extract, reroute, or cut over the local-backend PostgreSQL.

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

The adapter MUST record creator proof for resources it creates and MUST mutate, reconcile, recover, disable, delete, or clean up only resources proven to belong to its creation receipt. Adopted, external, and unproven resources MUST remain protected.

#### Scenario: Created resources are reconciled and cleaned

- GIVEN the adapter created Docker resources and retained a valid creation receipt
- WHEN reconciliation, recovery, rollback, or cleanup runs
- THEN only receipt-owned resources are considered
- AND successful cleanup leaves no adapter-owned residuals

#### Scenario: Foreign resource is protected

- GIVEN a Docker resource is external, adopted, or lacks matching creator proof
- WHEN destructive recovery or cleanup is requested
- THEN the adapter refuses that resource
- AND reports a typed, redacted ownership outcome

### Requirement: Credential and Artifact Handoffs Remain Opaque

The adapter MUST obtain credentials only through `CAP-CREDENTIALS` and MUST keep them opaque outside the authorized target-side injection step. Backup outputs and restore inputs MUST use `CAP-DATA-ARTIFACTS` references; the adapter MUST validate restore readiness before mutation.

#### Scenario: Provision and restore use approved handoffs

- GIVEN a valid `CredentialHandle` and, for restore, a valid `DataArtifactRef`
- WHEN provisioning or restore is requested
- THEN the adapter completes using those references
- AND returned values, diagnostics, and evidence contain no plaintext credentials or artifact bytes

#### Scenario: Invalid restore input fails closed

- GIVEN a restore reference is unavailable, incoherent, or fails integrity validation
- WHEN restore readiness is checked
- THEN the operation fails before target mutation
- AND the failure is typed and redacted

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

Acceptance evaluation MUST remain false unless required real-Docker and ownership-safety evidence is present and genuine at runtime. Evidence that is missing, simulated, or otherwise unable to demonstrate those runtime properties MUST NOT support acceptance, even when all other evidence is complete. The acceptance test suite MUST explicitly exercise this negative policy.

#### Scenario: Missing real-Docker or ownership evidence blocks acceptance

- GIVEN all approval and lifecycle evidence is complete except required real-Docker or ownership evidence
- WHEN acceptance readiness is evaluated at runtime
- THEN acceptance remains false
- AND the missing evidence is reported as the blocking condition

#### Scenario: Simulated evidence blocks acceptance

- GIVEN otherwise complete evidence marks real-Docker or ownership behavior as simulated rather than runtime-proven
- WHEN acceptance readiness is evaluated at runtime
- THEN acceptance remains false
- AND the runtime test demonstrates the fail-closed result
