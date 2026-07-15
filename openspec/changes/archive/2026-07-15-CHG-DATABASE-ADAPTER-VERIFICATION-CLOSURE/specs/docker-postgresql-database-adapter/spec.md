# Delta for Docker PostgreSQL Database Adapter

## ADDED Requirements

### Requirement: Credential Cleanup Residuals Are Rollback-Incomplete

When cleanup of an opaque `credential-file` target leaves a residual, the adapter MUST produce the existing `RollbackIncompleteError` outcome even when container rollback succeeds. The outcome MUST preserve the rollback receipt, causal failure, and resource residuals, and MUST expose only the safe `credential-file` identifier. Paths, secrets, handles, descriptors, and equivalent sensitive material MUST NOT be observable in the error, receipt, diagnostics, or reports.

#### Scenario: Credential-file residual survives successful container rollback

- GIVEN provisioning fails and cleanup cannot remove the credential target
- WHEN all receipt-owned container rollback operations otherwise succeed
- THEN the adapter raises `RollbackIncompleteError`
- AND the outcome preserves the receipt and original failure cause with residual `credential-file`

#### Scenario: Cleanup diagnostics remain redacted

- GIVEN a credential target contains a secret and its cleanup fails
- WHEN the rollback-incomplete outcome is observed
- THEN only the opaque `credential-file` token is exposed
- AND neither the target path nor secret is observable

### Requirement: Runtime Evidence Must Prove Fail-Closed Acceptance

Acceptance evaluation MUST remain false unless required real-Docker and ownership-safety evidence is present and genuine at runtime. Evidence that is missing, simulated, or otherwise unable to demonstrate those runtime properties MUST NOT support acceptance, even when all other evidence is complete. The acceptance test suite MUST explicitly exercise this negative policy.

#### Scenario: Missing real-Docker or ownership evidence blocks acceptance

- GIVEN all approval and lifecycle evidence is complete except required real-Docker or ownership evidence
- WHEN acceptance readiness is evaluated at runtime
- THEN acceptance remains false
- AND the missing evidence is reported as the blocking condition

#### Scenario: Simulated evidence blocks acceptance

- GIVEN otherwise complete evidence marks real-Docker or ownership behavior as simulated rather than runtime-proven
- WHEN acceptance readiness is evaluated at runtime
- THEN acceptance remains false
- AND the runtime test demonstrates the fail-closed result

## MODIFIED Requirements

None. Existing parent requirements remain unchanged; PR4 integration MUST precede implementation of this delta.
