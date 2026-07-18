# Delta for Project Catalog Resolution

## MODIFIED Requirements

### Requirement: Resolved Catalog Result Shape

A successful resolved catalog result MUST provide the authoritative downstream inputs for the selected project/client record: manifest reference, source context, data-policy default, and target default.

Each resolved field MUST be present in the successful result and MUST originate from catalog authority or catalog-declared defaults. A required string default (data-policy default, target default) that is present but blank or whitespace-only MUST be treated as missing, not as a materialized value, so that empty data can never reach downstream consumers as if it were authoritative. Downstream consumers MUST be able to consume the same resolved result without re-implementing manifest lookup, source-context selection, data-policy defaulting, or target defaulting.

The resolved result MAY include identifying metadata needed to trace the authority that produced it, but it MUST NOT require consumers to infer missing required fields.

(Previously: required resolved fields were only checked for absence via `None`; a present-but-blank string default was not treated as missing and could reach the resolved result as empty data.)

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

#### Scenario: Blank required default is treated as missing

- GIVEN a catalog record whose data-policy default or target default is present but blank or whitespace-only
- WHEN project-catalog resolution runs
- THEN the system MUST fail with an explicit invalid-catalog outcome
- AND the failure classification MUST be indistinguishable from the same field being absent
- AND it MUST NOT return a result carrying the blank value as an authoritative default
