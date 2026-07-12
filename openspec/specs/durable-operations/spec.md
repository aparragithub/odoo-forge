# Durable Operations Specification

## Purpose

Define a reusable capability contract for long-running and crash-sensitive operations so workflows can rely on stable identity, monotonic progress, authoritative terminal outcomes, recovery, compensation boundaries, and redacted durable evidence without coupling to a specific persistence implementation.

## Requirements

### Requirement: Stable Operation Identity and Replay Safety

The system MUST treat each durable operation as a stable operation identity bound to a single request meaning. Replays using the same operation identity and the same request meaning MUST be handled safely without creating a second authoritative operation. Reuse of an existing operation identity with different request meaning MUST be rejected as a conflict.

#### Scenario: Safe replay of the same request

- GIVEN a durable operation identity already recorded for a request meaning
- WHEN the same operation identity is submitted again with the same request meaning
- THEN the system MUST treat the submission as a replay of the existing durable operation
- AND the system MUST NOT create a second authoritative operation for that identity

#### Scenario: Conflict on mismatched replay

- GIVEN a durable operation identity already recorded for a request meaning
- WHEN the same operation identity is submitted with different request meaning
- THEN the system MUST reject the submission as a conflict
- AND the system MUST preserve the previously recorded durable operation unchanged

### Requirement: Monotonic Operation Lifecycle

The system MUST represent durable operations with a monotonic lifecycle that distinguishes accepted, in-flight, terminal, and cleanup-required work. Once an operation reaches a later lifecycle state, the system MUST NOT transition it back to an earlier state.

#### Scenario: Forward-only lifecycle progression

- GIVEN a durable operation in an accepted or in-flight state
- WHEN progress is recorded for that operation
- THEN the resulting lifecycle state MUST be the same or later in the lifecycle
- AND the system MUST NOT regress the operation to an earlier state

#### Scenario: Cleanup obligation remains visible after terminal work

- GIVEN an operation has reached a terminal business outcome but still has cleanup obligations
- WHEN the durable outcome is published
- THEN the system MUST represent the operation as cleanup-required or equivalent residual state
- AND the cleanup obligation MUST remain durably visible until resolved

### Requirement: Durable Checkpoints for Safe Resume

The system MUST support durable checkpoints that capture resume-safe progress for an in-flight operation. Recovery logic MUST use durable checkpoints to resume or reconcile work and MUST NOT require blindly repeating an unsafe mutation when a prior checkpoint already exists.

#### Scenario: Resume from a recorded checkpoint

- GIVEN an in-flight operation with a durable checkpoint describing resume-safe progress
- WHEN recovery is started after an interruption
- THEN the system MUST use the recorded checkpoint to determine the next valid recovery action
- AND the system MUST NOT require the workflow to restart from the beginning solely because of the interruption

#### Scenario: Unknown progress without a new checkpoint

- GIVEN an operation was interrupted after a mutation attempt and no later checkpoint was durably recorded
- WHEN recovery is started
- THEN the system MUST treat the missing progress as unknown rather than assumed success
- AND the system MUST require reconciliation or another safe recovery path before declaring an authoritative outcome

### Requirement: Authoritative Terminal Commit

The system MUST publish terminal outcome, durable evidence, and cleanup obligations atomically as one authoritative terminal commit. If the system cannot durably publish all required terminal information together, it MUST NOT expose a partial terminal result as authoritative.

#### Scenario: Successful terminal publication

- GIVEN an operation has reached a terminal outcome and has evidence and cleanup obligations to record
- WHEN the terminal commit succeeds
- THEN the outcome, evidence, and cleanup obligations MUST become durably visible together as one authoritative result

#### Scenario: Partial terminal publication is prevented

- GIVEN an operation has reached a terminal outcome
- WHEN the system cannot durably publish the full terminal commit
- THEN the system MUST NOT expose success or failure as authoritative by itself
- AND the operation MUST remain recoverable or reconcilable until a complete terminal commit exists

### Requirement: Workflow-Level Recovery and Reconciliation

The system MUST define workflow-level recovery and reconciliation semantics for interrupted or unknown-outcome operations. Recovery and reconciliation MUST distinguish workflow-level decisions from provider-level reconciliation inputs so downstream workflows can compose both without ambiguity.

#### Scenario: Recovery of an interrupted workflow

- GIVEN a durable operation is not in an authoritative terminal state after an interruption
- WHEN recovery is initiated
- THEN the system MUST provide enough durable state to resume, reconcile, or declare residual work according to workflow-level semantics
- AND the system MUST NOT require downstream workflows to invent their own durability model

#### Scenario: Provider reconciliation remains a separate concern

- GIVEN a workflow depends on provider-reported operation status during recovery
- WHEN workflow-level reconciliation is evaluated
- THEN the system MUST allow provider reconciliation data to inform the decision
- AND the system MUST keep the workflow-level authoritative outcome contract separate from the provider-specific status contract

### Requirement: Ownership-Aware Compensation Boundaries

The system MUST define compensation so that cleanup or rollback actions operate only on resources owned by the durable operation invocation that recorded them. The system MUST NOT remove, alter, or claim unrelated resources during compensation.

#### Scenario: Compensating owned resources

- GIVEN a durable operation has recorded resources it created or owns for compensation purposes
- WHEN compensation is executed
- THEN the system MUST target only those invocation-owned resources
- AND the compensation outcome MUST be durably recorded

#### Scenario: Unowned resources are protected

- GIVEN a related external resource was not recorded as owned by the durable operation invocation
- WHEN compensation is evaluated
- THEN the system MUST NOT treat that resource as compensable by default
- AND any remaining cleanup gap MUST be represented as durable residual work when relevant

### Requirement: Residual Cleanup Visibility

The system MUST record failed, incomplete, or deferred cleanup as durable residual work rather than best-effort logging. Residual cleanup state MUST remain visible for later recovery, reconciliation, or operator handling until resolved.

#### Scenario: Cleanup failure becomes residual work

- GIVEN an operation reaches a terminal business outcome but a required cleanup action fails
- WHEN the cleanup failure is recorded
- THEN the system MUST create durable residual cleanup state for that operation
- AND the cleanup failure MUST remain visible after the original business outcome is known

### Requirement: Redacted Durable Evidence

The system MUST persist durable evidence in a redacted form suitable for recovery, reconciliation, and audit without storing secrets, connection material, or protected data bytes. Durable evidence SHOULD retain only the minimum information needed to explain progress, outcome, and cleanup obligations.

#### Scenario: Evidence is stored without secrets

- GIVEN an operation records durable evidence for progress or terminal outcome
- WHEN that evidence is persisted
- THEN the stored evidence MUST exclude secrets, connection material, and protected data bytes
- AND the evidence MUST remain sufficient to support recovery, reconciliation, or audit of the operation
