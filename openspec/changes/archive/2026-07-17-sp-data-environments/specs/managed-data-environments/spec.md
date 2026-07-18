# Managed Data Environments Specification

## Purpose

Define the provider-neutral outcome contract for policy-compliant managed data environments without implementing prerequisite capabilities. Docker PostgreSQL is the decided first database adapter, but adapter-specific behavior remains prerequisite-owned.

## Requirements

### Requirement: Coherent Environment Identity

The system MUST treat a database and its filestore as one logical environment. It MUST expose an environment as usable only when both components and their shared identity and lineage are complete and consistent.

#### Scenario: Coherent environment becomes usable

- GIVEN a requested environment has a complete database and filestore pair
- WHEN their identity and lineage are durably bound
- THEN the environment is exposed as usable

#### Scenario: Partial or mismatched copy

- GIVEN either component is absent, partial, or has incompatible lineage
- WHEN the operation reaches its terminal state
- THEN the target MUST NOT be exposed as usable

### Requirement: Default Anonymization and Exception Evidence

The system MUST anonymize non-production data by default. It MUST permit an exception only when durable evidence records the actor, reason, source, destination, approval, and resulting outcome; denied or incomplete exceptions MUST NOT expose a target.

#### Scenario: Default non-production copy

- GIVEN a non-production environment is requested without an approved exception
- WHEN source data is copied
- THEN the resulting environment is anonymized before it is usable

#### Scenario: Incomplete exception evidence

- GIVEN an exception lacks any required evidence field or approval
- WHEN use of non-anonymized data is requested
- THEN the system fails closed and exposes no target

### Requirement: Idempotent Lifecycle and Safe Compensation

The system MUST make retried lifecycle operations idempotent. On failure, it MUST preserve sources and pre-existing resources, remove only targets owned by the failed invocation, and record residual cleanup required when removal cannot complete.

#### Scenario: Retried provision request

- GIVEN an invocation is retried with the same operation identity
- WHEN its prior terminal result is known
- THEN the system returns that result without creating another target

#### Scenario: Cleanup cannot complete

- GIVEN a failed invocation owns a target that cannot be removed
- WHEN compensation runs
- THEN sources and pre-existing resources remain unchanged and residual cleanup is recorded

### Requirement: Reference-Only Control-Plane Lineage

The control plane MUST store references, operation outcomes, and lineage for each environment. It MUST NOT store database bytes or filestore bytes.

#### Scenario: Record a usable environment

- GIVEN a coherent environment has become usable
- WHEN its outcome is recorded
- THEN the control plane stores references and lineage without data bytes

### Requirement: Fail-Closed Availability and Integrity

The system MUST fail closed when a required provider, artifact, policy decision, approval, or consistency check is unavailable or invalid. It MUST NOT expose an incomplete target or claim a successful outcome.

#### Scenario: Required dependency is unavailable

- GIVEN a requested operation cannot obtain a required dependency
- WHEN the operation is evaluated
- THEN no target is exposed as usable and the outcome records failure

### Requirement: Acceptance Dependency Gates

The managed-data-environments outcome MUST NOT be implemented or accepted as complete until approved contracts and acceptance evidence are available from `CHG-FIRST-DATABASE-ADAPTER`, `WF-DATA-COPY`, and `SP-CONTROL-PLANE-AUTHORITY`, including their stated gates: `PORT-DATABASE-PROVIDER`, `CAP-CREDENTIALS`, `CAP-DATA-ARTIFACTS`, `INT-DATABASE-RUNTIME-CUTOVER`, `CAP-DURABLE-OPERATIONS`, and `CAP-RESOURCE-OWNERSHIP`. `DPROV-DB` has selected Docker PostgreSQL as the exactly one first database adapter; this selection MUST NOT weaken the provider-neutral outcome contract or imply that any prerequisite handoff has been accepted.

#### Scenario: Prerequisite handoff is incomplete

- GIVEN any required handoff lacks approved contract or acceptance evidence
- WHEN outcome acceptance is assessed
- THEN acceptance is blocked without absorbing the prerequisite implementation

#### Scenario: First adapter is selected but handoffs remain incomplete

- GIVEN `DPROV-DB` has selected Docker PostgreSQL as the exactly one first database adapter
- WHEN implementation readiness is assessed
- THEN implementation remains blocked until every required handoff has approved contract and acceptance evidence
