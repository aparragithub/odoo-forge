# Tenancy Contract Specification

## Purpose

Define the normative platform tenancy contract so every downstream capability shares one answer for tenant identity, subordinate scopes, isolation expectations, quota authority, ownership composition, error semantics, and readiness to consume tenant scope.

## Requirements

### Requirement: Canonical Tenant Identity Type

The system MUST define a pure tenant identity value type keyed by a stable `tenant_id` representing the customer/client. This type MUST live under `src/odoo_forge/tenancy/` as a plain value type with no provider, adapter, or runtime dependency. Downstream capabilities MUST treat `tenant_id` as the sole canonical technical identifier and MUST NOT redefine project, environment class, provider account, or backend target as a peer tenant identity.

#### Scenario: Tenant identity value is constructed

- GIVEN a valid `tenant_id` string
- WHEN the tenant identity type is instantiated
- THEN it exposes `tenant_id` as an immutable, canonical field

#### Scenario: Peer identity is proposed

- GIVEN a downstream change proposes project or provider account as tenant identity
- WHEN conformance is checked against this type
- THEN the proposal is rejected as a redefinition of canonical tenant identity

### Requirement: Project Is the Sole v1 Subordinate Scope

The system MUST define a project scope type subordinate to exactly one `tenant_id`. In v1 this MUST be the only subordinate scope type provided by the contract. A project value MUST NOT be constructible without an associated `tenant_id`, and PROD/QA/DEV MUST remain operational classifications outside this type, never independent tenancy units.

#### Scenario: Project scope requires tenant association

- GIVEN a project value is constructed
- WHEN it lacks an associated `tenant_id`
- THEN construction fails as non-conformant

#### Scenario: Environment family is proposed as subordinate scope

- GIVEN a design introduces PROD/QA/DEV as a v1 subordinate tenancy scope
- WHEN it is checked against this contract
- THEN it is rejected

### Requirement: Operational Classifications Do Not Define Tenancy

The system MUST treat PROD, QA, and DEV as operational classifications that consume tenant scope rather than define tenancy. The system MUST NOT treat environment family as a normative v1 tenancy concept. Operational classifications MAY affect lifecycle behavior, lineage, or guardrails, but they MUST NOT create independent tenancy boundaries.

#### Scenario: Request type is evaluated

- GIVEN a request for PROD, QA, or DEV behavior
- WHEN tenancy boundaries are determined
- THEN the request remains inside the existing tenant scope

#### Scenario: Environment family is proposed as a tenancy boundary

- GIVEN a design introduces environment family as a normative tenant unit in v1
- WHEN tenancy conformance is reviewed
- THEN the design is rejected

### Requirement: Isolation Boundary Declaration

The system MUST declare tenant scope as the minimum isolation boundary that any consumer of these types honors for tenant-owned state and resources. The declaration MUST be provider-neutral, describing isolation as an outcome (no cross-tenant visibility or mutation) rather than a provider-specific mechanism. Downstream capabilities MAY add stricter isolation but MUST NOT weaken this boundary.

#### Scenario: Isolation outcome is described

- GIVEN the isolation boundary declaration
- WHEN a consumer reads it to build enforcement
- THEN it finds an outcome-level guarantee with no provider-specific detail

#### Scenario: Provider-native isolation is proposed as the contract

- GIVEN a change defines isolation only in provider-native terms
- WHEN reviewed against this requirement
- THEN it is rejected for violating provider neutrality

### Requirement: Ownership Composition Types

The system MUST provide ownership composition values `created`, `adopted`, and `external` that compose with, and do not replace, `tenant_id`. A `created` value MUST be attributable to the owning tenant scope. An `adopted` value MUST carry adoption evidence while remaining governed by the adopting tenant scope. An `external` value MUST record the tenant relationship while remaining externally owned, and MAY stay tenant-unattributed until adoption occurs.

#### Scenario: Created resource composes with tenant

- GIVEN a resource is marked `created`
- WHEN ownership is evaluated
- THEN it is attributable to exactly one tenant scope

#### Scenario: External resource stays unattributed pre-adoption

- GIVEN an `external` resource has not yet been adopted
- WHEN tenancy attribution is evaluated
- THEN it MAY remain tenant-unattributed without violating the contract

### Requirement: Quota Authority Declared Exactly Once

The system MUST declare, exactly once, that `CAP-TENANCY` is the sole authority for tenant-level quota policy. This declaration MUST NOT enumerate concrete quota dimensions (e.g., instance counts, storage, concurrency); dimensions belong to future consumer capabilities. Downstream capabilities MAY read or enforce quota outcomes but MUST NOT introduce a competing quota authority.

#### Scenario: Consumer seeks quota authority

- GIVEN a downstream capability needs to know where quota policy originates
- WHEN it inspects this contract
- THEN it finds `CAP-TENANCY` declared as sole authority, with no dimensions defined here

#### Scenario: Downstream capability defines its own quota model

- GIVEN a consumer introduces new tenant quota semantics
- WHEN reviewed against this requirement
- THEN it is rejected as a duplicate quota authority

### Requirement: Normative Tenancy Error Types

The system MUST define pure error types under `src/odoo_forge/tenancy/errors.py` for: unknown tenant, project referenced without tenant association, and cross-tenant access. A quota-exceeded error type MUST also be defined to reserve the surface, though enforcement is deferred to future consumers. These types MUST carry no provider or adapter dependency.

#### Scenario: Unknown tenant is referenced

- GIVEN an operation references a `tenant_id` with no corresponding tenant
- WHEN tenancy validation runs
- THEN the unknown-tenant error type is raised

#### Scenario: Cross-tenant access is attempted

- GIVEN a consumer attempts to access a resource scoped to a different tenant
- WHEN tenancy validation runs
- THEN the cross-tenant-access error type is raised

### Requirement: Downstream Consumers Must Consume and Must Not Redefine

The system MUST require SP-3, SP-4, and SP-8 to consume tenant identity, project subordination, isolation expectations, ownership composition, and quota authority from `CAP-TENANCY`. Downstream consumers MAY define behavior within tenant scope for their own concern, but they MUST NOT redefine tenant identity, create alternative subordinate authority models, redefine operational classifications as tenancy units, or move quota authority out of this capability.

#### Scenario: SP-3 consumes tenancy for provider enforcement

- GIVEN SP-3 defines backend-provider behavior
- WHEN it needs tenancy semantics
- THEN it treats `CAP-TENANCY` as the source contract and limits itself to consumer behavior inside that boundary

#### Scenario: SP-8 attempts to redefine tenancy semantics

- GIVEN SP-8 introduces its own tenant or quota definitions
- WHEN dependency conformance is checked
- THEN the change is rejected until it consumes `CAP-TENANCY` instead

### Requirement: Acceptance Evidence for Tenancy Readiness

The system MUST define an acceptance gate named `AC-CAP-TENANCY-READY`. This gate MUST require evidence that the canonical tenant unit is the customer/client, `tenant_id` is the stable technical identifier, project is the only normative subordinate scope in v1, PROD/QA/DEV are operational classifications rather than tenancy units, ownership composition with `created`/`adopted`/`external` is preserved, quota authority is defined exactly once here, normative tenancy error types are declared, and downstream consumers are positioned to consume rather than redefine the contract. Downstream spec or design work that depends on tenancy MAY rely on this capability only after that evidence is approved.

#### Scenario: Readiness evidence is complete

- GIVEN the tenancy contract and all required evidence are approved
- WHEN `AC-CAP-TENANCY-READY` is evaluated
- THEN downstream tenancy-dependent work may proceed

#### Scenario: Readiness evidence is incomplete

- GIVEN any required tenancy decision or consumer-boundary evidence is missing
- WHEN `AC-CAP-TENANCY-READY` is evaluated
- THEN downstream tenancy-dependent work remains blocked
