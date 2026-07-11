# Credential Materialization Specification

## Purpose

Define the first-store contract for resolving opaque credential handles into short-lived usable secrets without exposing plaintext to consumers, refs, state, logs, diagnostics, or acceptance evidence.

## Requirements

### Requirement: First Store Decision Gate

The system MUST treat `DPROV-SECRETS` as a prerequisite decision that selects exactly one approved first credential store for this capability. `AC-CAP-CREDENTIALS-READY` SHALL NOT advance until that store choice, scope, and approval evidence are recorded. This capability MUST NOT require multi-store support unless the approved store cannot satisfy the requirements below.

#### Scenario: Approved first store is recorded

- GIVEN `DPROV-SECRETS` has an approved first-store choice with recorded scope and evidence
- WHEN credential-capability readiness is evaluated
- THEN the store decision precondition is satisfied

#### Scenario: Store decision is missing

- GIVEN no approved `DPROV-SECRETS` choice is recorded
- WHEN `AC-CAP-CREDENTIALS-READY` is evaluated
- THEN readiness remains blocked

### Requirement: Handle-Only Consumer Boundary

The system MUST require consumers to accept and return only `CredentialHandle` values or opaque target-side injection references derived from them. Consumer contracts, provider values, plans, refs, receipts, and persisted control-plane state MUST NOT embed plaintext credential material.

#### Scenario: Consumer receives an opaque handoff

- GIVEN a downstream consumer needs credentials
- WHEN it interacts with the capability
- THEN the consumer receives only a handle or opaque injection reference

#### Scenario: Plaintext-bearing consumer shape is rejected

- GIVEN a proposed consumer contract or persisted value includes plaintext credentials
- WHEN contract conformance is evaluated
- THEN the shape is rejected

### Requirement: Materialization Boundary and Plaintext Lifetime

The system MUST allow plaintext credential material to exist only inside the credential capability, or inside the final target-native injection step it authorizes, while one resolution or injection operation is active. Plaintext MUST NOT be persisted and MUST be unavailable once that operation completes or fails.

#### Scenario: Resolution completes without persistence

- GIVEN a valid handle is resolved for one target operation
- WHEN resolution and injection complete
- THEN plaintext is not present in any returned or persisted value

#### Scenario: Failed operation clears temporary plaintext

- GIVEN a resolution or injection attempt fails
- WHEN the operation terminates
- THEN no plaintext remains available through capability outputs or durable state

### Requirement: Redacted Failures and Diagnostics

The system MUST redact plaintext secrets from logs, diagnostics, errors, receipts, and operator-visible evidence. Failures MAY identify the handle, operation, or target, but MUST NOT reveal secret values or reconstructable fragments.

#### Scenario: Failure is reported with redaction

- GIVEN credential resolution or injection fails
- WHEN diagnostics are emitted
- THEN the observable failure contains no plaintext secret material

### Requirement: Target-Side Injection Handoff

The system MUST support a handoff where a consumer supplies a `CredentialHandle` and a target context, and the resulting request carries only an opaque injection descriptor or store reference. If a target cannot accept a ref-only handoff, the system MUST fail closed rather than downgrade to consumer-visible plaintext.

#### Scenario: Ref-only target handoff succeeds

- GIVEN a target can consume an opaque injection reference
- WHEN the consumer submits a handle for that target
- THEN the handoff contains no plaintext credential material

#### Scenario: Non-ref-capable target fails closed

- GIVEN a target requires consumer-visible plaintext to proceed
- WHEN injection is requested
- THEN the request is rejected without exposing plaintext

### Requirement: Acceptance Evidence for Credential Readiness

The system MUST provide acceptance evidence for `AC-CAP-CREDENTIALS-READY` covering the approved `DPROV-SECRETS` choice, handle-only consumer boundaries, materialization limits, plaintext lifetime, redaction behavior, and target-side injection handoff. Downstream changes MAY rely on this capability only after that evidence is approved.

#### Scenario: Complete evidence advances readiness

- GIVEN every required approval and verification artifact is recorded
- WHEN `AC-CAP-CREDENTIALS-READY` is assessed
- THEN the acceptance gate may advance

#### Scenario: Incomplete evidence blocks downstream use

- GIVEN any required approval or verification artifact is absent
- WHEN downstream readiness depends on `AC-CAP-CREDENTIALS-READY`
- THEN downstream acceptance remains blocked
