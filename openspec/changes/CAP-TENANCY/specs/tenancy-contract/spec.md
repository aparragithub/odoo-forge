# Delta for Tenancy Contract

## ADDED Requirements

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
