# Delta for Credential Materialization

## MODIFIED Requirements

### Requirement: Materialization Boundary and Plaintext Lifetime

The system MUST allow plaintext credential material only inside the credential capability or the final target-native injection step while one operation is active. Docker PostgreSQL injection MUST NOT persist plaintext in `Config.Env`, inspect-visible configuration, returned values, or durable state. Plaintext MUST be unavailable after success or failure.
(Previously: plaintext was limited to the capability or final target-native injection step and was not persisted.)

#### Scenario: Docker injection leaves no environment credential
- GIVEN a valid handle targets Docker PostgreSQL
- WHEN credential materialization and injection complete
- THEN Docker `Config.Env`, outputs, and durable state contain no plaintext credential

#### Scenario: Failed operation clears temporary plaintext
- GIVEN resolution or injection fails
- WHEN the operation terminates
- THEN no plaintext remains available through capability outputs, Docker inspection, or durable state

### Requirement: Target-Side Injection Handoff

The system MUST support a `CredentialHandle` plus target context producing only an opaque Docker injection descriptor or supported secret/file reference. If the target cannot consume that ref-only mechanism, the system MUST fail closed rather than expose plaintext.
(Previously: targets received an opaque injection descriptor or store reference.)

#### Scenario: Ref-only Docker handoff succeeds
- GIVEN Docker PostgreSQL supports the approved secret/file mechanism
- WHEN the consumer submits a handle for that target
- THEN the handoff contains no plaintext and `Config.Env` contains no password

#### Scenario: Non-ref-capable target fails closed
- GIVEN a target requires consumer-visible plaintext or an unsupported legacy mechanism
- WHEN injection is requested
- THEN the request is rejected without exposing plaintext
