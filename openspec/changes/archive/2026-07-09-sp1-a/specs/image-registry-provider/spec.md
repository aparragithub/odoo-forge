# image-registry-provider Specification

## Purpose

Define the first immutable image identity capability for GHCR so operators can resolve and validate digest-backed image references before any runtime pull or backend integration exists.

## Requirements

### Requirement: Resolve GHCR image references to immutable digests

The system MUST provide a CLI flow that resolves a supported GHCR image reference into a canonical immutable digest reference.

#### Scenario: Resolve a mutable tag

- GIVEN an operator provides a valid GHCR tag reference
- WHEN the operator runs the resolve command
- THEN the system returns the matching immutable digest reference
- AND the command exits successfully

#### Scenario: Reject an unsupported registry reference

- GIVEN an operator provides a non-GHCR image reference
- WHEN the operator runs the resolve command
- THEN the system rejects the request with a clear unsupported-registry diagnostic

### Requirement: Validate immutable GHCR digest references

The system MUST provide a CLI flow that validates whether a GHCR digest reference is well formed and remotely resolvable.

#### Scenario: Validate an existing digest reference

- GIVEN an operator provides a valid GHCR digest reference that exists
- WHEN the operator runs the validate command
- THEN the system reports the reference as valid
- AND the command exits successfully

#### Scenario: Reject a malformed digest reference

- GIVEN an operator provides a malformed digest reference
- WHEN the operator runs the validate command
- THEN the system fails fast with a single-cause malformed-reference diagnostic

### Requirement: Surface fail-fast operator diagnostics

The system MUST fail fast and SHALL emit operator-readable diagnostics for registry access failures, with GHCR authentication failure treated as a priority case.

#### Scenario: GHCR authentication fails

- GIVEN the provided GHCR credentials are missing, invalid, or unauthorized
- WHEN the operator runs resolve or validate
- THEN the system exits on the auth failure without retry chaining
- AND the diagnostic explicitly identifies the failure as GHCR authentication related

#### Scenario: Image reference is not found

- GIVEN an operator provides a well-formed GHCR reference that does not exist
- WHEN the operator runs resolve or validate
- THEN the system exits with a not-found diagnostic that distinguishes it from auth and format errors

### Requirement: Preserve SP1-A scope boundaries

The system MUST limit this capability slice to digest resolve and validate behavior and MUST NOT introduce image pull execution, backend integration, multi-registry behavior, or `project.lock` persistence.

#### Scenario: Operator uses the first registry CLI

- GIVEN the digest resolve and validate commands are available
- WHEN an operator uses either command
- THEN the system performs only identity resolution or validation behavior
- AND no runtime pull or backend side effect is triggered

#### Scenario: Successful resolve completes

- GIVEN a resolve command succeeds
- WHEN the command finishes
- THEN no `project.lock` persistence is created or modified
- AND no additional registry implementation is required beyond GHCR in this slice
