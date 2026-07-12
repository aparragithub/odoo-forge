# Project Catalog Resolution Specification

## Purpose

Define the authoritative contract that resolves a client/project request into one accepted catalog result for downstream consumers. This capability owns project/client lookup, default resolution, and failure rules only; it does not own workflow orchestration, tenancy, provider choice, control-plane persistence, or data-artifact behavior.

## Requirements

### Requirement: Authoritative Project/Client Resolution

The system MUST expose one authoritative project-catalog resolution capability that accepts client/project identifying inputs and returns at most one accepted catalog result.

The capability MUST define which identifiers are sufficient to select a catalog record. A request that does not identify exactly one valid catalog record MUST NOT produce a resolved result.

When multiple catalog records match the supplied identifiers, the capability MUST treat the request as ambiguous and fail loudly instead of applying consumer-specific tie-breaking. When no catalog record matches, the capability MUST return a typed not-found outcome. When the matched record is invalid or incomplete for required resolution outputs, the capability MUST return a typed invalid-catalog outcome.

#### Scenario: Resolve one unique catalog record

- GIVEN a request whose client/project identifiers match exactly one valid catalog record
- WHEN project-catalog resolution runs
- THEN the system MUST return one resolved catalog result
- AND it MUST identify the matched catalog record as the authority for downstream defaults

#### Scenario: Reject ambiguous identifiers

- GIVEN a request whose supplied identifiers match more than one catalog record
- WHEN project-catalog resolution runs
- THEN the system MUST fail with an explicit ambiguous-resolution outcome
- AND it MUST NOT choose a record by fallback ordering, source order, or consumer-specific policy

#### Scenario: Reject missing catalog record

- GIVEN a request whose supplied identifiers match no catalog record
- WHEN project-catalog resolution runs
- THEN the system MUST fail with an explicit not-found outcome
- AND it MUST NOT synthesize a result from downstream defaults alone

### Requirement: Resolved Catalog Result Shape

A successful resolved catalog result MUST provide the authoritative downstream inputs for the selected project/client record: manifest reference, source context, data-policy default, and target default.

Each resolved field MUST be present in the successful result and MUST originate from catalog authority or catalog-declared defaults. Downstream consumers MUST be able to consume the same resolved result without re-implementing manifest lookup, source-context selection, data-policy defaulting, or target defaulting.

The resolved result MAY include identifying metadata needed to trace the authority that produced it, but it MUST NOT require consumers to infer missing required fields.

#### Scenario: Successful result includes all authoritative defaults

- GIVEN a request that resolves to one valid catalog record
- WHEN the successful catalog result is returned
- THEN the result MUST include the authoritative manifest reference
- AND the result MUST include the authoritative source context
- AND the result MUST include the authoritative data-policy default
- AND the result MUST include the authoritative target default

#### Scenario: Incomplete catalog record is rejected

- GIVEN a catalog record selected by the request but missing a required resolved field
- WHEN project-catalog resolution runs
- THEN the system MUST fail with an explicit invalid-catalog outcome
- AND it MUST NOT return a partial success result

### Requirement: Catalog-Owned Defaults and Failure Semantics

The project catalog MUST be the authority for lookup and default resolution within this capability boundary. Downstream workflows SHALL consume the resolved result and SHALL NOT redefine fallback rules for manifest reference, source context, data-policy default, or target default.

The capability MUST make fallback behavior explicit. If a resolved field comes from a catalog-declared default rather than an explicit per-record value, the successful result MUST preserve that authoritative outcome as resolved, not as consumer work left to interpret.

Failure outcomes MUST be stable enough for downstream consumers to distinguish ambiguity, absence, and invalid catalog authority without inspecting internal implementation details.

#### Scenario: Consumer reuses catalog defaults without reinterpreting them

- GIVEN a successful resolved catalog result whose target default came from a catalog-declared default
- WHEN a downstream consumer reads that result
- THEN the consumer MUST treat the returned target default as authoritative
- AND it MUST NOT rerun its own target-selection fallback logic

#### Scenario: Different failure classes remain distinguishable

- GIVEN one request is ambiguous and another request selects an invalid catalog record
- WHEN both resolution attempts fail
- THEN the returned outcomes MUST remain distinguishable by failure class
- AND downstream consumers MUST NOT need to parse internal error text to tell them apart

### Requirement: Capability Boundary Enforcement

This capability MUST remain bounded to authoritative client/project resolution and MUST NOT absorb concerns owned by tenancy, control-plane persistence, provider selection, request orchestration, or data-artifact lifecycle behavior.

A successful or failed catalog resolution result MAY be consumed by onboarding, environment-request, or control-plane capabilities, but this capability itself MUST NOT define those workflows.

#### Scenario: Resolution completes without request orchestration semantics

- GIVEN a consumer needs project/client resolution before starting an onboarding or environment-request workflow
- WHEN the consumer invokes project-catalog resolution
- THEN the result MUST be limited to authoritative resolution outputs and failure semantics
- AND it MUST NOT require this capability to define approvals, orchestration steps, persistence flows, or provider choice

### Requirement: Readiness Evidence for Downstream Consumers

The change acceptance evidence for `AC-CAP-PROJECT-CATALOG-READY` MUST demonstrate that the catalog contract is sufficient for downstream consumers to obtain one authoritative catalog result without inventing their own lookup or defaulting rules.

That evidence MUST show the accepted identifiers, the successful resolved result shape, the distinguishable failure classes, and the explicit boundary separating this capability from onboarding, environment requests, control-plane persistence, tenancy, provider selection, and data-artifact behavior.

#### Scenario: Acceptance evidence proves downstream readiness

- GIVEN the capability is presented as satisfying `AC-CAP-PROJECT-CATALOG-READY`
- WHEN acceptance evidence is reviewed
- THEN the evidence MUST show how one client/project request resolves to one authoritative catalog result
- AND it MUST show how ambiguity, absence, and invalid catalog authority are handled
- AND it MUST show the capability boundary exclusions that keep downstream workflow concerns out of scope
