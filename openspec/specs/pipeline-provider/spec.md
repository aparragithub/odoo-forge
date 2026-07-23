# Pipeline Provider Specification

## Purpose

Define the provider-neutral structural port contract that `odoo_forge` core
depends on to define/trigger pipeline (CI) runs, query run status, and
retrieve run outputs/logs — without importing or naming any concrete CI
engine. Adapters are out of scope; only the abstract interface and its
neutrality invariant are specified here.

## Requirements

### Requirement: Structural Pipeline Port

The system MUST expose a `runtime_checkable` `Protocol` named
`PipelineProvider` in `src/odoo_forge/ports/pipeline_provider.py` that core
code depends on exclusively through structural typing, with no import of any
concrete adapter.

#### Scenario: Structural conformance via isinstance

- GIVEN a plain class that implements every method the port declares, with
  matching method names
- WHEN checked with `isinstance(fake, PipelineProvider)`
- THEN the check MUST pass without the fake class inheriting from
  `PipelineProvider`

#### Scenario: Non-conforming object is rejected

- GIVEN an object missing one or more of the port's declared methods
- WHEN checked with `isinstance(obj, PipelineProvider)`
- THEN the check MUST fail

### Requirement: Pipeline Run Lifecycle Capability

The port MUST define operations sufficient to: (a) define/trigger a pipeline
run from a provider-neutral specification, (b) query the status of a run
already triggered, and (c) retrieve a triggered run's outputs/logs. Exact
method names/signatures are a design decision, not fixed by this spec.

#### Scenario: Trigger, poll, retrieve happy path

- GIVEN a structurally conforming fake `PipelineProvider` and a
  provider-neutral pipeline spec/run reference
- WHEN a run is triggered, its status is queried, and its output/log is
  retrieved via the port's declared methods
- THEN each call MUST return a provider-neutral result type (no CI-engine
  vocabulary in the returned shape)

#### Scenario: Status query for unknown run

- GIVEN a run reference not recognized by the fake provider
- WHEN status is queried for that reference
- THEN the port's contract MUST allow the implementation to signal
  "not found" (e.g. raise or return a distinct status) without requiring any
  CI-engine-specific error type at the port level

### Requirement: CI-Engine Neutrality Invariant

The port module, any domain types it references, and their docstrings MUST
NOT name or assume a specific CI engine (e.g. no vendor-specific product
names, YAML dialects, or subprocess/CLI wiring for a specific engine). All
vocabulary MUST stay at the level of "pipeline", "run", "status", "output" —
provider-neutral terms only.

#### Scenario: Docstring-boundary assertion

- GIVEN the source text of `pipeline_provider.py` (module + any pipeline
  domain-type modules)
- WHEN scanned for a fixed denylist of CI-engine-specific tokens
- THEN none of the denylisted tokens MUST appear

#### Scenario: No adapter import

- GIVEN the port module's import statements
- WHEN inspected
- THEN no import of a concrete CI adapter or CI-engine-specific package MUST
  be present
