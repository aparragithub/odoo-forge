# Tenancy Contract Specification

## Purpose

Define the normative platform tenancy contract so every downstream capability shares one answer for tenant identity, subordinate scopes, isolation expectations, quota authority, ownership composition, and readiness to consume tenant scope.

## Requirements

### Requirement: Canonical Tenant Identity

The system MUST define the tenant as the customer/client. Each tenant MUST be represented by a stable technical identifier named `tenant_id`. Downstream capabilities MAY carry additional business labels or display names, but they MUST treat `tenant_id` as the canonical technical identifier and MUST NOT redefine project, environment class, provider account, or backend target as a peer tenancy unit.

#### Scenario: Consumer receives canonical tenant scope

- GIVEN a downstream capability accepts tenant-scoped input
- WHEN the capability evaluates tenancy identity
- THEN it uses `tenant_id` as the canonical identifier for the customer/client tenant

#### Scenario: Alternate tenancy unit is proposed

- GIVEN a downstream change proposes project, provider account, or backend target as the tenant
- WHEN conformance to the tenancy contract is reviewed
- THEN the proposal is rejected as a redefinition of the canonical tenant unit

### Requirement: Project Is the Only Normative Subordinate Scope in v1

The system MUST define project as a scope subordinate to exactly one tenant. In v1, project SHALL be the only normative subordinate scope defined by this capability. A project MUST NOT exist without tenant association, and a project MUST NOT override or replace tenant authority.

#### Scenario: Project is evaluated within tenant scope

- GIVEN a project is referenced by a downstream capability
- WHEN scope validity is checked
- THEN the project is valid only as a child scope of one tenant

#### Scenario: Consumer attempts project-only authority

- GIVEN a downstream consumer processes a project without tenant association
- WHEN the tenancy contract is applied
- THEN the consumer is non-conformant

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

### Requirement: Minimum Tenant Isolation Contract

The system MUST define tenant scope as the minimum isolation boundary that downstream consumers honor for tenant-owned state, access surfaces, and provider-facing resources. Downstream capabilities MAY add stricter isolation within a tenant, but they MUST NOT weaken, bypass, or reinterpret the tenant boundary defined here. This capability MUST remain provider-neutral and MUST describe isolation outcomes rather than provider-specific mechanisms.

#### Scenario: Downstream capability consumes the isolation contract

- GIVEN a downstream capability provisions or registers tenant-scoped resources
- WHEN it applies tenancy rules
- THEN it preserves separation between resources and state belonging to different tenants

#### Scenario: Provider-specific mechanism is proposed as the contract

- GIVEN a change defines tenancy isolation only in provider-native terms
- WHEN the tenancy contract is reviewed
- THEN the change is rejected for violating provider neutrality

### Requirement: Ownership Semantics Compose With Tenant Authority

The system MUST compose tenant authority with existing ownership semantics `created`, `adopted`, and `external` without replacing them. `created` resources MUST be attributable to the tenant scope that requested or owns them. `adopted` resources MUST retain explicit adoption evidence while remaining governed within the adopting tenant scope. `external` resources MUST remain externally owned while recording the tenant relationship required for safe downstream use. Downstream consumers MUST NOT reinterpret these ownership labels to change tenancy authority.

#### Scenario: Created resource is recorded

- GIVEN a tenant-scoped resource is created by the platform
- WHEN ownership is evaluated
- THEN the resource is classified as `created` and attributable to that tenant scope

#### Scenario: External resource is consumed

- GIVEN a tenant uses a resource classified as `external`
- WHEN downstream consumers evaluate ownership and tenancy
- THEN they preserve the external ownership label and the tenant relationship together

### Requirement: Quota Authority Is Defined Exactly Once

The system MUST define quota authority at `CAP-TENANCY` exactly once. Tenant-level quota attachment, evaluation semantics, and downstream consumption rules MUST originate from this capability. Downstream capabilities MAY read, evaluate, enforce, or report quota outcomes within their own responsibilities, but they MUST NOT redefine quota scope, invent competing authorities, or introduce parallel quota models.

#### Scenario: Downstream consumer checks quota

- GIVEN a downstream capability needs quota information for a tenant-scoped action
- WHEN it evaluates quota
- THEN it consumes the quota contract defined by `CAP-TENANCY`

#### Scenario: Downstream capability proposes its own quota model

- GIVEN SP-3, SP-4, SP-8, or another consumer defines new tenant quota semantics
- WHEN the change is reviewed against this capability
- THEN the change is rejected as a duplicate quota authority

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

The system MUST define an acceptance gate named `AC-CAP-TENANCY-READY`. This gate MUST require evidence that the canonical tenant unit is the customer/client, `tenant_id` is the stable technical identifier, project is the only normative subordinate scope in v1, PROD/QA/DEV are operational classifications rather than tenancy units, ownership composition with `created`/`adopted`/`external` is preserved, quota authority is defined exactly once here, and downstream consumers are positioned to consume rather than redefine the contract. Downstream spec or design work that depends on tenancy MAY rely on this capability only after that evidence is approved.

#### Scenario: Readiness evidence is complete

- GIVEN the tenancy contract and all required evidence are approved
- WHEN `AC-CAP-TENANCY-READY` is evaluated
- THEN downstream tenancy-dependent work may proceed

#### Scenario: Readiness evidence is incomplete

- GIVEN any required tenancy decision or consumer-boundary evidence is missing
- WHEN `AC-CAP-TENANCY-READY` is evaluated
- THEN downstream tenancy-dependent work remains blocked
