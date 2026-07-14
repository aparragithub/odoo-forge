# Delta for Durable Operations

## MODIFIED Requirements

### Requirement: Residual Cleanup Visibility

The system MUST record failed, incomplete, or deferred cleanup as durable residual work rather than best-effort logging. Residual cleanup state MUST remain visible for later recovery, reconciliation, or operator handling until resolved. Resolving a residual cleanup obligation MUST NOT erase the operation's authoritative terminal outcome or its redacted evidence: a record whose cleanup has been resolved MUST still expose the terminal outcome and evidence that were established when the residual obligation was created.
(Previously: resolving cleanup only had to stay visible until resolved; it said nothing about what survives after resolution, which allowed the terminal outcome and evidence to be discarded on resolution.)

#### Scenario: Cleanup failure becomes residual work

- GIVEN an operation reaches a terminal business outcome but a required cleanup action fails
- WHEN the cleanup failure is recorded
- THEN the system MUST create durable residual cleanup state for that operation
- AND the cleanup failure MUST remain visible after the original business outcome is known

#### Scenario: Cleanup obligation stays visible while unresolved

- GIVEN a terminal commit carries non-empty residual cleanup evidence
- WHEN the operation's lifecycle is recorded as cleanup-required
- THEN the system MUST accept the record as valid
- AND the residual cleanup obligation MUST remain durably visible until resolved

#### Scenario: Resolved cleanup retains the terminal outcome and evidence

- GIVEN a terminal commit with non-empty residual cleanup was recorded for an operation
- WHEN the residual cleanup obligation is resolved and the lifecycle becomes closed
- THEN the system MUST accept a closed record that still carries that terminal commit
- AND the terminal outcome and its redacted evidence MUST remain durably visible on the closed record

#### Scenario: A closed record with no terminal work is still valid

- GIVEN an operation was closed without ever recording a terminal commit
- WHEN the closed record is inspected
- THEN the system MUST accept the record as valid
- AND the absence of a terminal commit MUST NOT be treated as a violation

#### Scenario: Closed records without residual cleanup keep the unchanged invariant

- GIVEN a terminal commit carries empty residual cleanup
- WHEN the operation's lifecycle is recorded as closed
- THEN the system MUST reject the record
- AND only a lifecycle equal to the terminal commit's outcome MUST be accepted for that empty-residual terminal commit

### Requirement: Authoritative Terminal Commit

The system MUST publish terminal outcome, durable evidence, and cleanup obligations atomically as one authoritative terminal commit. If the system cannot durably publish all required terminal information together, it MUST NOT expose a partial terminal result as authoritative. A terminal lifecycle outcome MUST NOT become authoritative through any path that bypasses the terminal commit and its durable evidence.
(Previously: the requirement described atomic publication and partial-publication prevention but did not state that terminal outcomes are unreachable outside the terminal-commit path.)

#### Scenario: Successful terminal publication

- GIVEN an operation has reached a terminal outcome and has evidence and cleanup obligations to record
- WHEN the terminal commit succeeds
- THEN the outcome, evidence, and cleanup obligations MUST become durably visible together as one authoritative result

#### Scenario: Partial terminal publication is prevented

- GIVEN an operation has reached a terminal outcome
- WHEN the system cannot durably publish the full terminal commit
- THEN the system MUST NOT expose success or failure as authoritative by itself
- AND the operation MUST remain recoverable or reconcilable until a complete terminal commit exists

#### Scenario: Evidence-free terminal transition is rejected

- GIVEN an operation is not yet in an authoritative terminal state
- WHEN a transition to a terminal outcome is attempted without durable evidence for that outcome
- THEN the system MUST reject the transition
- AND the operation MUST remain in a non-authoritative-terminal lifecycle state

### Requirement: Workflow-Level Recovery and Reconciliation

The system MUST define workflow-level recovery and reconciliation semantics for interrupted or unknown-outcome operations. Recovery and reconciliation MUST distinguish workflow-level decisions from provider-level reconciliation inputs so downstream workflows can compose both without ambiguity. The set of workflow-level recovery actions MUST be exactly resume, reconcile, surface residual work, and no recovery required; the system MUST NOT define a compensation-triggering recovery action.

A recovery decision for an already-resolved operation MUST report that no recovery is required. An operation is resolved when it holds an authoritative terminal outcome with no open residual obligation, or when its residual obligation has been closed. The system MUST NOT ask a workflow to resume or reconcile an operation that is already resolved.
(Previously: the requirement described recovery and reconciliation semantics without bounding the set of recovery actions, and produced no decision at all for resolved operations — they fell through to resume or reconcile.)

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

#### Scenario: Recovery actions are bounded

- GIVEN a workflow-level recovery decision is produced for any durable operation state
- WHEN the resulting recovery action is inspected
- THEN the action MUST be one of resume, reconcile, surface residual work, or no recovery required
- AND no compensation-triggering recovery action MUST be offered

#### Scenario: A resolved operation requires no recovery

- GIVEN a durable operation holds an authoritative terminal outcome with no open residual obligation, or its residual obligation has been closed
- WHEN a workflow-level recovery decision is requested for it
- THEN the decision MUST report that no recovery is required
- AND the decision MUST NOT be resume or reconcile, even when a durable checkpoint is present and a mutation was attempted
