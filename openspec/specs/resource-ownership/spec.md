# Resource Ownership Contract Specification

## Purpose

Define the normative, provider-neutral platform contract for resource ownership so every downstream capability shares one answer for ownership state, receipt/evidence shape, tenant attribution, operation-identity composition, and the read/attest port surface, closing readiness gate `AC-CAP-RESOURCE-OWNERSHIP-READY`.

## Requirements

### Requirement: Canonical Ownership State Model

The system MUST define resource ownership using exactly three states — `created`, `adopted`, `external` — generalized from the existing `ResourceOwnership` enum (`src/odoo_forge/database/types.py`) from database scope to any managed resource kind (databases, backend containers, image registry entries, future remote/K8s targets). The system MUST NOT introduce additional ownership states such as `reserved` or `pending` in v1.

#### Scenario: Resource kind adopts the three-state model

- GIVEN a new resource kind (e.g. a backend container) needs an ownership classification
- WHEN it is expressed against `CAP-RESOURCE-OWNERSHIP`
- THEN it is classified as exactly one of `created`, `adopted`, or `external`

#### Scenario: A new state is proposed

- GIVEN a downstream change proposes a `reserved` or `pending` ownership state
- WHEN conformance to this contract is reviewed
- THEN the proposal is rejected as an unauthorized extension of the v1 state model

### Requirement: Ownership Vocabulary Generalizes the Existing Anchor Without Replacing It

The system MUST treat `src/odoo_forge/database/types.py`'s `ResourceOwnership`, `DatabaseRef`, and `CreationReceipt` as the vocabulary anchor for this contract. The generalization MUST lift the vocabulary to platform scope additively; it MUST NOT replace, rewrite, or relocate the existing database-scoped types or the existing Docker `LocalOwnershipAuthority` / `provider.py` enforcement.

#### Scenario: Platform-scoped model is derived from the anchor

- GIVEN the platform-scoped ownership state model is authored
- WHEN it is compared against `src/odoo_forge/database/types.py`
- THEN its state names and semantics are consistent with `ResourceOwnership` and do not introduce a competing model

#### Scenario: Change proposes rewriting the Docker adapter

- GIVEN a change proposes rewriting or relocating `LocalOwnershipAuthority` or `provider.py` as part of this contract
- WHEN the change is reviewed against this capability
- THEN the change is rejected as out of scope for `CAP-RESOURCE-OWNERSHIP`

### Requirement: Verifiable Ownership Receipt

The system MUST define an ownership receipt/evidence shape generalized from `CreationReceipt`, composed of an opaque operation proof, the set of owned resource ids, and a live-proof expectation. The receipt MUST be sufficient to prove ownership is verifiable. The concrete live-proof mechanism (e.g. Docker labels) MUST remain an adapter concern and MUST NOT be normative in this contract.

#### Scenario: Adapter satisfies the receipt shape

- GIVEN an adapter creates or adopts a resource
- WHEN it issues an ownership receipt
- THEN the receipt carries an opaque operation proof, the owned resource ids, and an expectation that live proof can be produced

#### Scenario: Receipt omits live-proof mechanism

- GIVEN a receipt is defined by this contract
- WHEN the concrete live-proof mechanism is specified
- THEN the mechanism is left to the adapter and is not encoded as a normative rule here

### Requirement: Tenant Attribution Composes With Ownership Without Mandatory Linkage

The system MUST define tenant attribution as composition with, not replacement of, ownership state, consuming tenant identity from `CAP-TENANCY`. A resource classified as `created` or `adopted` MAY carry a tenant link. A resource classified as `external`, and any pre-tenancy resource, MAY remain tenant-unattributed until it is adopted. Downstream consumers MUST NOT treat a tenant link as mandatory at ownership time.

#### Scenario: External resource remains tenant-unattributed

- GIVEN a resource is classified as `external`
- WHEN ownership is evaluated before adoption
- THEN the resource MAY have no tenant link and remains valid under this contract

#### Scenario: Adoption establishes tenant attribution

- GIVEN a tenant-unattributed `external` resource is adopted
- WHEN adoption evidence and a tenant link are recorded together
- THEN the resource becomes attributable to that tenant while its ownership state transitions per adapter-level rules

#### Scenario: Consumer requires a tenant link at ownership time

- GIVEN a downstream consumer rejects a resource solely because it lacks a tenant link at creation or external-registration time
- WHEN conformance to this contract is reviewed
- THEN the consumer's requirement is rejected as a violation of the composition rule

### Requirement: Operation Identity Composes With `CAP-DURABLE-OPERATIONS` Without Duplication

The system MUST reuse the operation-identity and receipt model defined by `CAP-DURABLE-OPERATIONS` for ownership evidence rather than authoring a competing identity model. The opaque operation proof in an ownership receipt MUST be expressible in terms of `CAP-DURABLE-OPERATIONS`' stable operation identity.

#### Scenario: Ownership receipt reuses durable operation identity

- GIVEN an adapter issues an ownership receipt for a durably tracked operation
- WHEN the receipt's operation proof is constructed
- THEN it is derived from the `CAP-DURABLE-OPERATIONS` operation identity rather than a new identity scheme

#### Scenario: Change proposes a parallel operation-identity model

- GIVEN a change defines a new operation-identity or replay-safety model for ownership evidence
- WHEN it is reviewed against this capability
- THEN the change is rejected as a duplicate of `CAP-DURABLE-OPERATIONS`

### Requirement: `PORT-RESOURCE-OWNERSHIP` Exposes Read/Attest Semantics Only

The system MUST define a provider-neutral `PORT-RESOURCE-OWNERSHIP` surface in `src/odoo_forge/ports/` expressing ownership state and receipt/evidence read and attestation semantics. The port v1 MUST NOT define runtime authority for transition verbs (`reserve`, `bind`, `activate`, `retire`, `adopt`); those verbs MAY be described narratively as future composition points, but their runtime authority is deferred to `SP-CONTROL-PLANE-AUTHORITY`.

#### Scenario: Consumer reads ownership state and evidence

- GIVEN an adapter implements `PORT-RESOURCE-OWNERSHIP`
- WHEN a consumer queries ownership state and receipt evidence for a resource
- THEN the port returns the ownership state and receipt without requiring any transition-verb authority

#### Scenario: Change adds a transition verb to the v1 port contract

- GIVEN a change adds `reserve`, `bind`, `activate`, `retire`, or `adopt` as an executable v1 port method
- WHEN the change is reviewed against this capability
- THEN the change is rejected until runtime transition authority is defined by `SP-CONTROL-PLANE-AUTHORITY`

### Requirement: Downstream Consumers Must Consume and Must Not Redefine

The system MUST require `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY` to consume the ownership state model, receipt shape, tenant-attribution composition, and `PORT-RESOURCE-OWNERSHIP` surface from `CAP-RESOURCE-OWNERSHIP`. These consumers MAY define behavior within their own concern (runtime authority, lifecycle/retention, workflow orchestration) but MUST NOT redefine ownership states, the receipt shape, or tenant-attribution composition.

#### Scenario: SP-CONTROL-PLANE-AUTHORITY consumes the ownership contract

- GIVEN `SP-CONTROL-PLANE-AUTHORITY` defines runtime ownership authority
- WHEN it needs ownership state or evidence semantics
- THEN it consumes `CAP-RESOURCE-OWNERSHIP` as the source contract and adds only transition-verb authority

#### Scenario: A downstream change redefines ownership states

- GIVEN `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, or `WF-DATA-COPY` introduces its own ownership state vocabulary
- WHEN dependency conformance is checked
- THEN the change is rejected until it consumes `CAP-RESOURCE-OWNERSHIP` instead

### Requirement: Acceptance Evidence for Resource Ownership Readiness

The system MUST define an acceptance gate named `AC-CAP-RESOURCE-OWNERSHIP-READY`. This gate MUST require evidence that: the ownership state model is generalized to exactly `created`/`adopted`/`external` at platform scope without new states; the receipt/evidence shape is reusable by any resource kind and free of Docker-label specifics; tenant attribution composes with ownership without mandatory linkage at ownership time; operation identity composes with `CAP-DURABLE-OPERATIONS` without duplication; `PORT-RESOURCE-OWNERSHIP` v1 exposes read/attest semantics only; and `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY` are positioned as consumers. Downstream spec or design work depending on resource ownership MAY rely on this capability only after that evidence is approved.

#### Scenario: Readiness evidence is complete

- GIVEN the resource-ownership contract and all required evidence are approved
- WHEN `AC-CAP-RESOURCE-OWNERSHIP-READY` is evaluated
- THEN `SP-CONTROL-PLANE-AUTHORITY`, `SP-RESOURCE-LIFECYCLE`, `WF-ENVIRONMENT-REQUEST`, and `WF-DATA-COPY` may proceed to spec/design

#### Scenario: Readiness evidence is incomplete

- GIVEN any required ownership-state, receipt, tenant-composition, or port-surface evidence is missing
- WHEN `AC-CAP-RESOURCE-OWNERSHIP-READY` is evaluated
- THEN downstream ownership-dependent work remains blocked
