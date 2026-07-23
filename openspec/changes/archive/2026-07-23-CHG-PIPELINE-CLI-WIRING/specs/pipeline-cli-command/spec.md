# Pipeline CLI Command Specification

## Purpose

Expose the existing `PipelineProvider` port (already implemented by
`GitHubActionsPipelineProvider`) through `forge` CLI commands, wired via the
composition root, mirroring the `image`/`backend`/`manifest` command
conventions. This is a NEW capability — no existing spec covers pipeline CLI
UX; `pipeline-provider` and `github-actions-pipeline-adapter` remain
unchanged.

## Requirements

### Requirement: Composition-Root Pipeline Provider Factory

The system MUST expose `_make_pipeline_provider()` in
`src/odoo_forge_cli/_composition.py` that constructs a
`GitHubActionsPipelineProvider` over a `GitHubActionsRestTransport`, sourcing
required configuration (token, owner, repo, ref) from environment variables.
The factory MUST NOT apply a silent default for the token value.

#### Scenario: Factory builds a provider when all required env vars are present

- GIVEN all required environment variables (token, owner, repo, ref) are set
- WHEN `_make_pipeline_provider()` is called
- THEN a `GitHubActionsPipelineProvider` instance is returned
- AND it is constructed with a `GitHubActionsRestTransport`

#### Scenario: Missing required env var raises a clear composition error

- GIVEN one or more required environment variables are unset
- WHEN `_make_pipeline_provider()` is called
- THEN the factory MUST raise an error identifying which variable is missing
- AND MUST NOT construct a provider with a placeholder or default token

### Requirement: Trigger Command

The system MUST expose a `trigger` Typer command that validates its
arguments, calls `_composition._make_pipeline_provider()`, invokes the
provider's `trigger` method with a neutral run spec built from the CLI args,
and echoes the resulting run reference.

#### Scenario: Trigger succeeds and prints the run reference

- GIVEN valid CLI arguments and required env vars present
- WHEN the `trigger` command is invoked
- THEN the provider's `trigger` method is called with a spec derived from the
  arguments
- AND the returned `PipelineRunRef` is printed via `typer.echo`
- AND the command exits with code 0

#### Scenario: Provider domain error surfaces as a single error line

- GIVEN valid CLI arguments but the provider raises its domain error type
- WHEN the `trigger` command is invoked
- THEN exactly one `error: ...` line is printed
- AND the command exits with code 1

### Requirement: Status Command

The system MUST expose a `status` Typer command that validates its
arguments, calls `_composition._make_pipeline_provider()`, invokes the
provider's `status` method with a run reference built from the CLI args, and
echoes the resulting run status.

#### Scenario: Status succeeds and prints the run status

- GIVEN a valid run reference argument and required env vars present
- WHEN the `status` command is invoked
- THEN the provider's `status` method is called with the given reference
- AND the returned `PipelineRunStatus` is printed via `typer.echo`
- AND the command exits with code 0

#### Scenario: Provider domain error surfaces as a single error line

- GIVEN a valid run reference argument but the provider raises its domain
  error type
- WHEN the `status` command is invoked
- THEN exactly one `error: ...` line is printed
- AND the command exits with code 1

### Requirement: Command Registration in main.py

The system MUST register the `pipeline` command module in
`src/odoo_forge_cli/main.py` via `pipeline.register(app)`, consistent with
`backend`, `image`, `maintenance`, and `manifest`.

#### Scenario: Pipeline commands are reachable from the root app

- GIVEN the `forge` CLI app is constructed
- WHEN its registered commands are inspected
- THEN the `trigger` and `status` pipeline commands are present and callable

### Requirement: Token Is Never Echoed

The system MUST NOT print the configured token value in any command output,
success or error path.

#### Scenario: Token absent from all command output

- GIVEN a token configured via environment variable
- WHEN `trigger` or `status` is invoked (success or error path)
- THEN the token value does not appear anywhere in stdout or stderr
