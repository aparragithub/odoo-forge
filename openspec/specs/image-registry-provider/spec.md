# image-registry-provider Specification

## Purpose

Define the platform image registry contract for publishing built images, resolving immutable digests, checking digest existence, and pre-pulling digest refs without duplicating backend runtime ownership.

## Requirements

### Requirement: Publish built images as immutable digests

The system MUST publish a Phase 1-built image reference and return an immutable digest without rebuilding the image.

#### Scenario: Publish returns a digest

- GIVEN a built image reference from the Phase 1 factory
- WHEN publish runs
- THEN the system returns an immutable digest reference

#### Scenario: Publish input is not publishable

- GIVEN the image reference is missing or not publishable
- WHEN publish runs
- THEN the system fails with a single-cause publish diagnostic

### Requirement: Pull digest references as a registry concern only

The system MUST pull a digest reference into a local image handle and MUST NOT duplicate the Docker runtime pull owned by `DockerBackendProvider.run()`.

#### Scenario: Pull returns a local handle

- GIVEN an existing canonical digest reference
- WHEN pull runs
- THEN the system returns a local image handle

#### Scenario: Pull does not trigger backend runtime execution

- GIVEN the pull flow succeeds
- WHEN the command finishes
- THEN no backend `run/status/stop/logs/exec` action is triggered

### Requirement: Check digest existence without transfer

The system MUST provide an `exists` flow that checks whether a digest is present without transferring layers.

#### Scenario: Existing digest reports present

- GIVEN a valid digest that exists remotely
- WHEN exists runs
- THEN the system reports the digest as present

#### Scenario: Missing digest reports absent

- GIVEN a valid digest that does not exist remotely
- WHEN exists runs
- THEN the system reports the digest as absent without pulling layers

### Requirement: Resolve GHCR image references to immutable digests

The system MUST resolve a supported image reference in the chosen adapter into a canonical immutable digest reference. GHCR SHALL be the first adapter, but later adapters MUST preserve the same contract.

(Previously: resolution was GHCR-only identity lookup.)

#### Scenario: Resolve a mutable tag

- GIVEN a valid supported tag reference
- WHEN the resolve command runs
- THEN the system returns the matching immutable digest reference

#### Scenario: Reject an unsupported registry reference

- GIVEN a reference outside the chosen adapter
- WHEN the resolve command runs
- THEN the system rejects the request with a clear unsupported-registry diagnostic

### Requirement: Surface fail-fast diagnostics

The system MUST fail fast and SHALL emit readable diagnostics for publish, pull, resolve, and exists failures. Tests MUST distinguish malformed input, unsupported registry, not found, and auth failures.

(Previously: diagnostics covered only resolve/validate.)

#### Scenario: Registry authentication fails

- GIVEN registry credentials are missing, invalid, or unauthorized
- WHEN publish, pull, resolve, or exists runs
- THEN the system exits on the auth failure without retry chaining

#### Scenario: Image reference is not found

- GIVEN a well-formed reference that does not exist
- WHEN publish, pull, resolve, or exists runs
- THEN the system exits with a not-found or absent diagnostic distinct from auth and format errors

### Requirement: Preserve SP1-A scope boundaries

The system MUST extend the slice to publish, pull, resolve_digest, and exists, and MUST NOT introduce multi-registry fan-out, control-plane state, `project.lock` persistence, deprecated `PublishedLayer` cleanup, or duplicated Docker runtime pull behavior from `sp1-b`. Delivery SHOULD stay chained.

(Previously: the slice covered only resolve/validate and excluded pull behavior.)

#### Scenario: Operator uses the platform registry CLI foundation

- GIVEN publish, pull, resolve, and exists commands are available
- WHEN any command is used
- THEN the system performs only registry-port behavior for the chosen adapter

#### Scenario: Successful registry command completes

- GIVEN a registry command succeeds
- WHEN the command finishes
- THEN no `project.lock` persistence is created or modified
