# Database Provider Lifecycle Specification

## Purpose

Provide a provider-agnostic, safe production-to-QA database and filestore lifecycle.

## Requirements

### Requirement: Provider contract and references

The system MUST expose one runtime-checkable `DatabaseProvider` contract for provision, clone, randomize, and drop. Database and copy references MUST be immutable, retain source-to-destination lineage, and lifecycle failures MUST be typed.

#### Scenario: Provider satisfies the contract

- GIVEN a Dockerized PostgreSQL provider
- WHEN it is checked against `DatabaseProvider`
- THEN the runtime check succeeds and its lifecycle operations are available

#### Scenario: Copy failure is classified

- GIVEN a provider lifecycle operation fails
- WHEN the CLI reports the failure
- THEN it reports a typed error rather than an unclassified success

### Requirement: Dockerized PostgreSQL lifecycle

The system MUST deliver Dockerized PostgreSQL as its first provider and MUST provision, clone, randomize, and drop database resources through that provider.

#### Scenario: Provision a Docker database

- GIVEN a valid database reference
- WHEN an operator provisions it
- THEN the Dockerized PostgreSQL provider returns its immutable reference

#### Scenario: Randomize a cloned database

- GIVEN a cloned Docker database
- WHEN an operator requests randomization
- THEN the provider returns the typed lifecycle outcome

#### Scenario: Drop an absent database

- GIVEN a database resource is absent
- WHEN an operator drops it
- THEN the provider reports the typed lifecycle outcome without deleting other resources

### Requirement: Coordinated copy consistency

The system MUST create and validate the database and its Odoo filestore as one copy operation. It MUST NOT report partial success. On failure, it MUST report the outcome and remove only target resources created by that invocation; sources and pre-existing target resources MUST remain unchanged.

#### Scenario: Production copy reaches QA

- GIVEN an authorized production source and a QA destination
- WHEN the operator requests a copy
- THEN the destination has a validated database and matching filestore with recorded lineage

#### Scenario: Filestore copy fails

- GIVEN the database target was newly created and filestore creation fails
- WHEN recovery runs
- THEN the new target is cleaned up and source and pre-existing destination resources remain unchanged

### Requirement: Destination policy, authorization, and audit

Each destination MUST declare its own anonymization policy. Copying production data MUST require explicit authorization and MUST write a local audit entry containing actor, reason, source, destination, and result, including failed authorization.

#### Scenario: Authorized production-to-QA copy

- GIVEN QA declares an anonymization policy and the operator supplies authorization and reason
- WHEN the copy completes
- THEN that destination policy is applied and the local audit entry contains all required fields

#### Scenario: Production authorization is absent

- GIVEN a production source and no explicit authorization
- WHEN a copy is requested
- THEN no destination copy is created and the result is recorded in the local audit entry

### Requirement: Lifecycle command boundary

The system MUST expose lifecycle commands that use the configured provider and MUST NOT require runtime provider mixing.

#### Scenario: Command uses the configured provider

- GIVEN Dockerized PostgreSQL is configured
- WHEN an operator invokes a lifecycle command
- THEN the command performs the operation through that provider only
