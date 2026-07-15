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

The system MUST allow plaintext credential material only inside the credential capability or the final target-native injection step while one operation is active. Docker PostgreSQL injection MUST NOT persist plaintext in `Config.Env`, inspect-visible configuration, returned values, or durable state. Plaintext MUST be unavailable after success or failure.

#### Scenario: Docker injection leaves no environment credential

- GIVEN a valid handle targets Docker PostgreSQL
- WHEN credential materialization and injection complete
- THEN Docker `Config.Env`, outputs, and durable state contain no plaintext credential

#### Scenario: Failed operation clears temporary plaintext

- GIVEN resolution or injection fails
- WHEN the operation terminates
- THEN no plaintext remains available through capability outputs, Docker inspection, or durable state

### Requirement: Redacted Failures and Diagnostics

The system MUST redact plaintext secrets from logs, diagnostics, errors, receipts, and operator-visible evidence. Failures MAY identify the handle, operation, or target, but MUST NOT reveal secret values or reconstructable fragments.

#### Scenario: Failure is reported with redaction

- GIVEN credential resolution or injection fails
- WHEN diagnostics are emitted
- THEN the observable failure contains no plaintext secret material

### Requirement: Target-Side Injection Handoff

The system MUST support a `CredentialHandle` plus target context producing only an opaque Docker injection descriptor or supported secret/file reference. If the target cannot consume that ref-only mechanism, the system MUST fail closed rather than expose plaintext.

#### Scenario: Ref-only Docker handoff succeeds

- GIVEN Docker PostgreSQL supports the approved secret/file mechanism
- WHEN the consumer submits a handle for that target
- THEN the handoff contains no plaintext and `Config.Env` contains no password

#### Scenario: Non-ref-capable target fails closed

- GIVEN a target requires consumer-visible plaintext or an unsupported legacy mechanism
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
