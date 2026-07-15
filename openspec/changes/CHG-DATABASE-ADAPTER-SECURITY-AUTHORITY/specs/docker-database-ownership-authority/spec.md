# Docker Database Ownership Authority Specification

## Purpose

Define durable, local Docker ownership authority and non-forgeable runtime evidence.

## Requirements

### Requirement: Durable Protected Authority

The system MUST persist Docker ownership authority durably, without PostgreSQL credentials, with restrictive local custody and integrity protection. Missing, unreadable, corrupt, tampered, or lost authority MUST fail closed.

#### Scenario: Authority survives restart
- GIVEN a Docker resource and valid authority exist
- WHEN the process and Docker daemon restart
- THEN ownership verification succeeds from durable authority

#### Scenario: Authority integrity fails
- GIVEN authority is missing, unreadable, altered, or corrupt
- WHEN mutation, reconcile, rollback, or cleanup is requested
- THEN the operation fails closed with redacted ownership information

### Requirement: Authority-Backed Ownership Operations

Labels MAY identify candidates only. Mutation, reconcile, rollback, and cleanup MUST require verified authority; authority loss MUST NOT be recovered from labels or inspection data.

#### Scenario: Owned resource is cleaned
- GIVEN authority verifies ownership after restart
- WHEN cleanup or rollback runs
- THEN only authority-owned resources are changed

#### Scenario: Inspect-only candidate is rejected
- GIVEN labels or Docker inspection suggest ownership without authority
- WHEN a destructive operation is requested
- THEN the resource is rejected and may require recreation

### Requirement: Non-Importable Runtime Evidence

Acceptance evidence MUST be verifiable through durable authority and runtime observation. Importable, process-local, forged, or inspect-reconstructed evidence MUST NOT establish acceptance.

#### Scenario: Genuine evidence is accepted
- GIVEN authority and runtime checks verify the final resource lineage
- WHEN acceptance is evaluated
- THEN evidence is accepted without credential disclosure

#### Scenario: Forged evidence is rejected
- GIVEN evidence is imported, minted locally, or reconstructed from inspection
- WHEN acceptance is evaluated
- THEN acceptance remains false

### Requirement: Legacy Resource Rejection

Resources lacking the new authority MUST fail closed; legacy labels MUST provide no migration authority, and the adapter MUST require recreation.

#### Scenario: Legacy resource is encountered
- GIVEN a resource has legacy ownership labels but no valid authority
- WHEN reconciliation or use is requested
- THEN the resource is rejected and recreation is required

### Requirement: Final-Lineage Evidence

Verification and archive evidence MUST be regenerated against the final resource lineage after chained delivery and MUST NOT preserve stale predecessor evidence.

#### Scenario: Final lineage is archived
- GIVEN chained changes complete with changed resource lineage
- WHEN final verification and archive evidence are produced
- THEN evidence binds the final lineage and excludes stale lineage

### Requirement: Immutable Review Boundary

The system and delivery process MUST accept `review-e272dab2cf939ee5` findings as the governing security input and MUST NOT modify, recover, validate, reopen, or otherwise touch `review-093c1c067f361178`.

#### Scenario: Review boundary is enforced
- GIVEN security work is planned or verified
- WHEN review references are processed
- THEN only `review-e272dab2cf939ee5` is accepted and the prohibited review remains untouched
