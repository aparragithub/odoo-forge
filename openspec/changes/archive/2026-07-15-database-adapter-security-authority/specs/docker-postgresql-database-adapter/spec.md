# Delta for Docker PostgreSQL Database Adapter

## MODIFIED Requirements

### Requirement: Isolated Docker Lifecycle

The adapter MUST implement the accepted database lifecycle for Docker PostgreSQL and MUST be selectable only through `DPROV-DB`. It MUST remain additive and MUST NOT extract, reroute, or cut over the local-backend PostgreSQL. Provider-neutral contracts, opaque handoffs, typed redaction, and exclusions for tracker integration, control-plane authority, data environments, data copy, and PublishedLayer/Override semantics MUST remain unchanged.
(Previously: the adapter was additive and isolated from local-backend routing and adjacent scopes.)

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
(Previously: creator proof and creation receipts governed lifecycle ownership.)

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
(Previously: credentials were opaque outside an authorized target-side injection step.)

#### Scenario: Provision and restore use approved handoffs
- GIVEN a valid `CredentialHandle` and, for restore, a valid `DataArtifactRef`
- WHEN provisioning or restore is requested
- THEN the adapter completes using those references
- AND returned values, diagnostics, evidence, and Docker inspection expose neither credentials nor artifact bytes

#### Scenario: Invalid restore input fails closed
- GIVEN a restore reference is unavailable, incoherent, or fails integrity validation
- WHEN restore readiness is checked
- THEN the operation fails before target mutation and the failure is typed and redacted

### Requirement: Runtime Evidence Must Prove Fail-Closed Acceptance

Acceptance MUST remain false unless final-lineage real-Docker, authority, and ownership-safety evidence is genuine at runtime. Missing, simulated, imported, forged, stale, or inspection-reconstructed evidence MUST NOT support acceptance.
(Previously: required real-Docker and ownership-safety evidence had to be genuine at runtime.)

#### Scenario: Missing or stale evidence blocks acceptance
- GIVEN required final-lineage or authority evidence is missing or stale
- WHEN acceptance readiness is evaluated
- THEN acceptance remains false and the blocking condition is reported

#### Scenario: Simulated or forged evidence blocks acceptance
- GIVEN evidence is simulated, imported, or reconstructed from inspection
- WHEN acceptance readiness is evaluated
- THEN acceptance remains false and the runtime test demonstrates fail-closed behavior
