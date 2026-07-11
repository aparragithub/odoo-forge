# Database Provider Core Specification

## Purpose

Define pure database lifecycle contracts and the Docker PostgreSQL adapter. Runtime routing, governance decisions, and coordinated-copy behavior are excluded.

## Requirements

### Requirement: Canonical Provider Contract

The core MUST expose a runtime-checkable `DatabaseProvider` whose methods exactly match: `provision(spec: DatabaseSpec) -> DatabaseRef`, `clone(source_ref: DatabaseRef, target_spec: DatabaseSpec) -> DatabaseRef`, `randomize(source_ref: DatabaseRef, target_spec: DatabaseSpec, rules: AnonymizationRules) -> DatabaseRef`, and `drop(ref: DatabaseRef) -> None`.

#### Scenario: Adapter conforms
- GIVEN a Docker PostgreSQL adapter
- WHEN it is checked against the protocol and `inspect.signature`
- THEN runtime conformance and all four canonical signatures pass

#### Scenario: Signature drifts
- GIVEN an adapter with an added, removed, or differently annotated parameter
- WHEN conformance is evaluated
- THEN the adapter is rejected

### Requirement: Pure Lifecycle Values and Failures

`DatabaseSpec`, `DatabaseRef`, and lineage MUST be immutable and MUST contain neither database bytes nor resolved secret values; refs MAY contain a credential handle. `DatabaseSpec` MUST carry a stable operation ID and an opaque `NetworkAttachment` supplied by runtime integration; core and its adapter MUST NOT create, own, or remove runtime networks. The adapter MUST receive a `CredentialResolver` that materializes protected, temporary credential files as context-managed leases and guarantees cleanup. Resolved secrets MUST NOT appear in argv, logs, exceptions, refs, or receipts. Lifecycle failures MUST be typed and redacted.

#### Scenario: Reference lineage is retained
- GIVEN a clone or randomize result
- WHEN its ref and lineage are inspected
- THEN the source identity and operation identity are available without data bytes

#### Scenario: Invalid lifecycle request
- GIVEN an invalid spec or unavailable source
- WHEN an operation is requested
- THEN it raises the applicable typed lifecycle error without exposing a secret

#### Scenario: Runtime attachment and credential lease
- GIVEN a runtime-supplied network attachment and credential handle
- WHEN a lifecycle operation executes or fails
- THEN the adapter uses the attachment without owning it, transports credentials only through protected temporary files, and removes those files

### Requirement: Creation Outcomes and Capture Artifact

The canonical provider methods MUST return only `DatabaseRef` and clone/randomize only from live `DatabaseRef` sources. A companion `DatabaseCreationProvider` MUST use distinct tagged provision, captured-restore, and captured-randomize requests and return `CreatedDatabase` with a `CreationReceipt`. `DatabaseCaptureRef` MUST contain artifact identity, `application/vnd.odoo-forge.postgresql-dump`, format version `1`, SHA-256 digest, URI, and consistency boundary, but MUST NOT embed host, database name, credential, or another usable live-source ref. Core MUST provide restoration primitives but MUST NOT coordinate capture, validation, discard, filestore, or compensation.

#### Scenario: Created target is recorded
- GIVEN companion creation of a new target
- WHEN creation succeeds
- THEN the outcome atomically carries its ref and creator receipt

#### Scenario: Captured restore cannot fall back to live source
- GIVEN a valid capture artifact and its former live source is unavailable
- WHEN captured restore or captured randomization runs
- THEN restoration succeeds from the verified artifact alone and never attempts a live-source connection

#### Scenario: Pre-existing target is protected
- GIVEN a target represented without a creator-owned receipt
- WHEN a cleanup consumer requests removal
- THEN it preserves that target

### Requirement: Recoverable Ownership and Safe Cleanup

Creation MUST derive deterministic operation/resource identities and managed labels from the request operation ID. A typed reconciliation operation MUST inspect those labels and readiness to reconstruct a creator receipt after mutation-before-return. Reconciliation and rollback MUST report every teardown failure. `DatabaseRef` and receipts MUST distinguish `created`, `adopted`, and `external` ownership and carry a creator token only for `created`; canonical `drop` MUST verify the token against labels. A receipt-aware cleanup companion MUST distinguish compensation from deliberate canonical decommission and MUST preserve resources without verified creator ownership.

#### Scenario: Crash after target readiness
- GIVEN mutation committed but no result reached the caller
- WHEN reconciliation receives the same deterministic request identity
- THEN it reconstructs the ready target and creator receipt or reports typed residual cleanup failures

#### Scenario: Adopted or external target is protected
- GIVEN a ref without matching created ownership and token labels
- WHEN deliberate drop or compensation is requested
- THEN removal is refused without changing that resource

### Requirement: Docker PostgreSQL Lifecycle

`odoo_forge_postgres_docker` MUST provision, live-clone, captured-restore, randomize, and drop PostgreSQL databases on the supplied Docker network. It MUST use deterministic PostgreSQL 16 container/volume names and managed operation/ownership labels; explicit command timeouts and safe operation labels; readiness via `pg_isready`; SHA-256-before-mutation artifact verification; `pg_restore --single-transaction --exit-on-error` for custom dumps and `psql --single-transaction --set=ON_ERROR_STOP=1` for plain SQL; and a separate target-only transaction for ordered anonymization rules. Receipts MUST be returned only after restore/randomization commits and final readiness. Failures MUST roll back only verified operation-owned resources and raise typed, redacted errors including cleanup residuals. `AnonymizationRules` MUST remain pure execution input, not destination policy.

#### Scenario: Lifecycle round trip
- GIVEN a reachable Docker PostgreSQL source and target specs
- WHEN provision, clone, randomize, and drop run in sequence
- THEN each created ref is usable, flagged fields transform, unflagged fields remain, and the source remains unchanged

#### Scenario: Operation fails or cleanup runs
- GIVEN a failed clone/randomize or a pre-existing target
- WHEN error handling or receipt-based cleanup runs
- THEN typed failure is reported and only receipt-owned resources are removed

### Requirement: Adapter Isolation and Additive Coexistence

Core and its adapter package MUST enforce pure-core import boundaries. The addition MUST remain package-isolated and additive and MUST NOT alter Slice 4b runtime ownership, routing, configuration, or existing-resource preservation behavior. Configured-provider selection and runtime-mixing enforcement belong exclusively to umbrella acceptance `INT-CLI-01`.

#### Scenario: Additive package coexistence
- GIVEN the new adapter package and existing Slice 4b runtime
- WHEN import-boundary and legacy runtime tests execute
- THEN forbidden imports are absent and Slice 4b behavior remains unchanged without provider routing assertions

### Requirement: Reviewable Delivery and Real-Docker Proof

Contracts, receipts, recovery, and cleanup contracts MUST land before mutation adapters. Provision/recovery, drop/cleanup, live clone, captured restore, randomization, and real-Docker coverage MUST be autonomous tested chained slices below 400 changed lines. Adapter coverage MUST be included in coverage configuration. Real-Docker tests MUST execute substantive lifecycle, artifact-only restore, randomization, recovery, and ownership-preservation assertions when a daemon is available; they MAY skip only after a daemon probe reports the explicit unavailable reason.

#### Scenario: Integration environment is evaluated
- GIVEN the integration suite starts
- WHEN Docker is available
- THEN substantive adapter scenarios execute and contribute coverage
- AND when Docker is unavailable each skip reports the daemon-probe reason
