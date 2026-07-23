# GitHub Actions Pipeline Adapter Specification

## Purpose

Concrete `PipelineProvider` adapter (`odoo_forge_pipeline_github`) backed by
GitHub Actions. Implements the neutral `PipelineProvider` port (PORT-PIPELINE)
without leaking Actions-specific vocabulary, using an injectable transport
seam so tests are hermetic. This is a NEW capability; the `pipeline-provider`
port contract is unchanged.

## Requirements

### Requirement: Structural Protocol Conformance

The adapter's `GitHubActionsPipelineProvider` MUST satisfy the
`runtime_checkable` `PipelineProvider` Protocol via `isinstance` — i.e. expose
`trigger(spec)`, `status(ref)`, and `logs(ref)` methods.

#### Scenario: isinstance passes against the port

- GIVEN a `GitHubActionsPipelineProvider` constructed with a transport
- WHEN checked with `isinstance(provider, PipelineProvider)`
- THEN the check returns `True`

### Requirement: Trigger Maps to Workflow Dispatch

The adapter MUST translate a neutral `PipelineRunSpec` into a GitHub Actions
`workflow_dispatch` request via the injected transport and return a neutral
`PipelineRunRef` referencing the resulting run.

#### Scenario: Trigger dispatches a workflow run

- GIVEN a `PipelineRunSpec` with a workflow definition and parameters
- WHEN `trigger(spec)` is called
- THEN the transport receives a workflow_dispatch call carrying the spec's
  definition and parameters
- AND a `PipelineRunRef` is returned identifying the dispatched run

### Requirement: Status Maps GitHub Actions Run State Onto Neutral State

The adapter MUST map every GitHub Actions run `status`/`conclusion`
combination onto exactly one `PipelineRunState` value, covering all six
neutral states.

| GitHub Actions status/conclusion | Neutral `PipelineRunState` |
|---|---|
| `queued` | `pending` |
| `in_progress` | `running` |
| `completed` / `success` | `succeeded` |
| `completed` / `failure` | `failed` |
| `completed` / `cancelled` | `canceled` |
| any unrecognized or unmapped status/conclusion | `unknown` |

#### Scenario: Queued run maps to pending

- GIVEN a fake transport reporting run status `queued`
- WHEN `status(ref)` is called
- THEN a `PipelineRunStatus` with `state="pending"` is returned

#### Scenario: In-progress run maps to running

- GIVEN a fake transport reporting run status `in_progress`
- WHEN `status(ref)` is called
- THEN a `PipelineRunStatus` with `state="running"` is returned

#### Scenario: Completed success maps to succeeded

- GIVEN a fake transport reporting status `completed` with conclusion `success`
- WHEN `status(ref)` is called
- THEN a `PipelineRunStatus` with `state="succeeded"` is returned

#### Scenario: Completed failure maps to failed

- GIVEN a fake transport reporting status `completed` with conclusion `failure`
- WHEN `status(ref)` is called
- THEN a `PipelineRunStatus` with `state="failed"` is returned

#### Scenario: Completed cancelled maps to canceled

- GIVEN a fake transport reporting status `completed` with conclusion `cancelled`
- WHEN `status(ref)` is called
- THEN a `PipelineRunStatus` with `state="canceled"` is returned

#### Scenario: Unrecognized status maps to unknown

- GIVEN a fake transport reporting an unrecognized status/conclusion pair
- WHEN `status(ref)` is called
- THEN a `PipelineRunStatus` with `state="unknown"` is returned

### Requirement: Logs Return Accumulated Run Output

The adapter MUST retrieve the target run's accumulated log text via the
injected transport and return it as a plain string.

#### Scenario: Logs are retrieved for a run

- GIVEN a `PipelineRunRef` for a completed run
- WHEN `logs(ref)` is called
- THEN the transport is queried for that run's logs
- AND the returned value is the plain log text as a string

### Requirement: Injected Transport Seam — No Hidden Network

The adapter MUST accept its transport/HTTP-client dependency via
constructor injection and MUST NOT perform any network I/O outside that
injected seam. Unit tests MUST use a fake transport with zero live network
access.

#### Scenario: Adapter never calls network directly in tests

- GIVEN a `GitHubActionsPipelineProvider` constructed with a fake transport
- WHEN `trigger`, `status`, and `logs` are exercised in the test suite
- THEN no live HTTP/network call occurs
- AND all external interaction is observed only through the fake transport

### Requirement: Adapter Returns Only Provider-Neutral Types

The adapter's public methods MUST return only `odoo_forge.pipeline.types`
values (`PipelineRunRef`, `PipelineRunStatus`, `str`) and MUST NOT expose
GitHub-specific types (e.g. raw GitHub API response objects, GitHub run IDs
typed distinctly from `PipelineRunRef`, GitHub-specific status strings) to
callers.

#### Scenario: Return types are neutral, not GitHub-specific

- GIVEN any successful call to `trigger`, `status`, or `logs`
- WHEN the return value's type is inspected
- THEN it is exactly `PipelineRunRef`, `PipelineRunStatus`, or `str`
- AND no GitHub Actions-specific type or raw API payload is exposed

### Requirement: Packaging and Import-Linter Isolation

The adapter MUST be packaged as an isolated root package
(`odoo_forge_pipeline_github`) registered in `pyproject.toml`'s `packages`
and `root_packages`. A forbidden import-linter contract MUST prevent
`odoo_forge` core from importing the adapter.

#### Scenario: Core cannot import the adapter

- GIVEN the import-linter configuration in `pyproject.toml`
- WHEN import-linter contracts are checked
- THEN any import of `odoo_forge_pipeline_github` from `odoo_forge` is
  forbidden and the check fails if such an import is introduced

#### Scenario: Adapter package is registered and buildable

- GIVEN the project's `pyproject.toml`
- WHEN `packages` and `root_packages` are inspected
- THEN `src/odoo_forge_pipeline_github` and `odoo_forge_pipeline_github` are
  present, mirroring the `odoo_forge_registry` precedent
