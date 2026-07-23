# Delta for Portfolio State

State-data refresh only — no product capability changes. This delta captures verifiable
assertions about `docs/specs/platform/portfolio.json` after the refresh is applied.

## ADDED Requirements

### Requirement: Pipeline adapter items reflect achieved status

The system MUST record `PORT-PIPELINE`, `ADAPTER-PIPELINE-GITHUB`, and
`CHG-FIRST-PIPELINE-ADAPTER` in `docs/specs/platform/portfolio.json` with
`status: "achieved"`, a populated `evidence_date`, and non-empty `evidence`
entries referencing the merged GitHub Actions pipeline adapter work
(commit `890f8bb`).

#### Scenario: Pipeline items are synced after adapter merge

- GIVEN `docs/specs/platform/portfolio.json` currently marks `PORT-PIPELINE`,
  `ADAPTER-PIPELINE-GITHUB`, and `CHG-FIRST-PIPELINE-ADAPTER` as `proposed`
  with empty `evidence` and open `gaps`
- WHEN the portfolio refresh is applied
- THEN each of the three items MUST have `status: "achieved"`
- AND each MUST have a non-empty `evidence_date`
- AND each MUST have at least one `evidence` entry referencing the merged
  adapter commit, source, or tests

#### Scenario: Nested acceptance entries mirror item status

- GIVEN an item transitions to `achieved`
- WHEN its nested `acceptance[]` entries are inspected
- THEN each corresponding `acceptance[].status` MUST also be `achieved`
- AND its `evidence` MUST reference the same evidence source IDs as the parent item

### Requirement: Gaps are cleared for achieved items

The system MUST clear the `gaps` array for any item transitioned to `achieved`
in this refresh.

#### Scenario: G5 and G6 gaps are cleared

- GIVEN `PORT-PIPELINE` lists gap `G5` and `ADAPTER-PIPELINE-GITHUB` lists gap `G6`
- WHEN the refresh sets both items to `achieved`
- THEN their `gaps` arrays MUST be empty

### Requirement: Evidence catalog stays consistent

The system MUST NOT reference an evidence source ID in an item or acceptance
entry unless that ID exists in `meta.evidence_catalog`.

#### Scenario: Missing evidence source is added to the catalog

- GIVEN the refresh introduces a new evidence source ID for the pipeline adapter
- WHEN that ID does not already exist in `meta.evidence_catalog`
- THEN the refresh MUST add a corresponding entry to `meta.evidence_catalog`
- AND the entry MUST describe the evidence (commit, path, or test reference)

### Requirement: Unrelated portfolio state remains untouched

The system MUST NOT modify any `items`, `decisions`, `transitions`, or
`transfers` outside the three named pipeline-adapter items, including
`ADAPTER-PIPELINE-GITLAB` and `SP-DELIVERY-AUTOMATION`.

#### Scenario: GitLab adapter and delivery-automation outcome are unaffected

- GIVEN `ADAPTER-PIPELINE-GITLAB` and `SP-DELIVERY-AUTOMATION` exist in
  `portfolio.json` before the refresh
- WHEN the refresh is applied
- THEN both entries MUST remain byte-identical to their pre-refresh state

#### Scenario: No unrelated array elements change

- GIVEN the refresh only targets `PORT-PIPELINE`, `ADAPTER-PIPELINE-GITHUB`,
  and `CHG-FIRST-PIPELINE-ADAPTER`
- WHEN a diff of `portfolio.json` is produced after the refresh
- THEN the diff MUST NOT include changes to any other item, decision,
  transition, or transfer entry

### Requirement: Portfolio file remains valid JSON

The system MUST keep `docs/specs/platform/portfolio.json` as syntactically
valid, parseable JSON after the refresh.

#### Scenario: File parses successfully post-refresh

- GIVEN the refresh has been applied to `portfolio.json`
- WHEN the file is parsed with a standard JSON parser
- THEN parsing MUST succeed with no syntax errors

### Requirement: Refresh scope excludes source and tests

The system MUST NOT modify any file under `src/` or `tests/` as part of this
refresh.

#### Scenario: No source or test files are touched

- GIVEN the refresh is limited to portfolio state data
- WHEN the change is complete
- THEN no files under `src/` or `tests/` SHALL appear in the change diff
