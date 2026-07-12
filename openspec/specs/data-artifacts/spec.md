# Data Artifacts Specification

## Purpose

Define the prerequisite-only contract for opaque data artifact references so downstream restore and managed-environment capabilities can consume one accepted restore input while preserving database+filestore coherence, fail-closed validation, and ref-only control-plane compatibility.

## Requirements

### Requirement: Opaque Restore Reference

The system MUST define `DataArtifactRef` as one opaque capability-owned reference for restore consumers. A `DataArtifactRef` MUST identify one capability-owned restore set handle, not individual component bytes. The reference MUST be suitable for provider restore inputs and lineage storage, and MUST NOT embed artifact bytes, credential material, hostnames, or live-source connection details.

#### Scenario: Restore consumer accepts one opaque reference

- GIVEN a downstream restore consumer requests a restore input
- WHEN it receives a `DataArtifactRef`
- THEN it treats the value as one opaque restore set handle
- AND it does not require separate database and filestore references

#### Scenario: Secret-bearing or component-explicit reference is invalid

- GIVEN a proposed restore reference contains bytes, secrets, hostnames, live-source details, or separate component identifiers
- WHEN the capability contract is evaluated
- THEN the reference is rejected as non-conformant

### Requirement: Capability-Owned Restore Set Resolution

The system MUST resolve each accepted `DataArtifactRef` within the data-artifacts capability boundary to one coherence group that covers every artifact required for one usable restore target. For managed Odoo-like environments, that coherence group MUST include both the database capture and the filestore capture. Downstream consumers SHALL depend only on the opaque `DataArtifactRef` and SHALL NOT redefine the grouping model.

#### Scenario: One reference resolves to a coherent restore set

- GIVEN an accepted `DataArtifactRef`
- WHEN the capability resolves the reference
- THEN it yields one coherence group containing the database capture and filestore capture required for a usable target
- AND downstream consumers continue to use exactly one opaque input

#### Scenario: Partial component group is not accepted

- GIVEN a reference resolves to only a database capture or only a filestore capture
- WHEN coherence is evaluated
- THEN the capability fails resolution
- AND no consumer may treat the input as restore-ready

### Requirement: Capability-Owned Integrity Metadata

The system MUST own the integrity contract for every restore set resolved from a `DataArtifactRef`. The contract MUST include identity metadata, format or version markers, component membership, and checksum or digest evidence sufficient to validate the restore set and its required components without exposing artifact bytes.

#### Scenario: Integrity metadata proves required membership

- GIVEN a restore set resolved from a `DataArtifactRef`
- WHEN its metadata is inspected
- THEN the metadata identifies the restore set, its required components, and the digest or checksum evidence for those components
- AND it exposes no artifact bytes or secret-bearing values

#### Scenario: Missing integrity metadata blocks acceptance

- GIVEN a restore set lacks required identity, membership, format, or digest evidence
- WHEN integrity validation runs
- THEN validation fails closed
- AND the restore set is not accepted for restore

### Requirement: Pre-Mutation Restore Readiness

The system MUST validate availability, integrity, and coherence before any restore-side mutation begins. If the capability cannot prove that a `DataArtifactRef` resolves to a complete and available coherent restore set, downstream restore consumers MUST fail closed and MUST NOT mutate the target.

#### Scenario: Validation succeeds before mutation

- GIVEN a restore request references an accepted `DataArtifactRef`
- WHEN pre-mutation validation proves availability, integrity, and coherence
- THEN the restore input is marked restore-ready before mutation begins

#### Scenario: Coherence cannot be proven

- GIVEN a restore request references a `DataArtifactRef` whose resolved components are unavailable, mismatched, or incomplete
- WHEN pre-mutation validation runs
- THEN validation fails closed
- AND no restore-side mutation begins

### Requirement: Typed, Redacted Failure and Discard Outcomes

The system MUST define typed, redacted outcomes for validation failure, unavailable artifacts, coherence failure, discard refusal, discard completion, and residual discard failure. Discard authority and handoff semantics for resolved restore sets MUST be explicit so downstream consumers know when cleanup is capability-owned and when residual action remains, without exposing sensitive artifact details.

#### Scenario: Residual discard failure is reported safely

- GIVEN a resolved restore set is eligible for discard and one discard action cannot complete
- WHEN discard finishes
- THEN the outcome reports a typed residual failure
- AND the report remains redacted

#### Scenario: Validation failure does not leak artifact details

- GIVEN pre-mutation validation rejects a `DataArtifactRef`
- WHEN the failure is returned to a downstream consumer
- THEN the outcome is typed and redacted
- AND it does not disclose artifact bytes, secrets, or live-source details

### Requirement: Capability Readiness Evidence

The system MUST provide readiness evidence for opaque-reference conformance, restore set resolution, integrity metadata, pre-mutation fail-closed validation, and typed redacted discard outcomes. `AC-CAP-DATA-ARTIFACTS-READY` SHALL advance only when the approved proposal, this specification, and verification evidence identifiers are recorded.

#### Scenario: Complete evidence advances readiness

- GIVEN approved proposal, approved specification, and verification evidence identifiers are recorded
- WHEN capability readiness is evaluated
- THEN `AC-CAP-DATA-ARTIFACTS-READY` may advance

#### Scenario: Missing evidence preserves the gate

- GIVEN any required approval or verification evidence identifier is absent
- WHEN capability readiness is evaluated
- THEN `AC-CAP-DATA-ARTIFACTS-READY` remains blocked
