# Delta for Manifest

## ADDED Requirements

### Requirement: forge onboard supports mutually exclusive dispatch modes

`forge onboard` MUST accept exactly one of two input modes: `--manifest
<path>` (local-input mode) or a positional `<cliente>` argument
(catalog-driven mode). Supplying both `--manifest` and a positional client
argument in the same invocation MUST be rejected before either mode's logic
runs. Supplying neither MUST be rejected with the same class of error. Both
rejections MUST render a single `error:` line and exit non-zero, with no
partial work performed.

#### Scenario: Both manifest and client supplied

- GIVEN `forge onboard --manifest project.yaml some-client` is invoked
- WHEN the command parses its arguments
- THEN it MUST print a single `error:` line stating the modes are mutually
  exclusive
- AND it MUST exit non-zero without invoking `ProjectCatalogResolver` or the
  local-manifest pipeline

#### Scenario: Neither manifest nor client supplied

- GIVEN `forge onboard` is invoked with no `--manifest` option and no
  positional client argument
- WHEN the command parses its arguments
- THEN it MUST print a single `error:` line stating one input mode is
  required
- AND it MUST exit non-zero without invoking either pipeline

### Requirement: forge onboard --manifest keeps existing local-input behavior unchanged

`forge onboard --manifest <path>` MUST continue to validate the manifest,
materialize the workspace via the existing lock/projection pipeline, and
print the existing success/next-step output — with no catalog lookup and no
backend/instance creation. This mode's behavior MUST NOT change as part of
introducing the catalog-driven mode.

#### Scenario: Local-input mode behaves as before

- GIVEN a valid manifest, an existing lock, and no positional client
  argument
- WHEN `forge onboard --manifest project.yaml` runs
- THEN it materializes the workspace exactly as before and prints the
  existing "onboarded workspace ... / next: run \`forge validate\`" output
- AND it does not create or attempt to create any backend instance

### Requirement: forge onboard <cliente> resolves, materializes, and starts an instance

`forge onboard <cliente>` MUST resolve the supplied client identifier via
`ProjectCatalogResolver.resolve()` using the composition-root
`CatalogIndex` adapter. On a successful resolution it MUST reuse the
existing manifest/lock/projection pipeline (`plan_projection`,
`project_workspace`) to materialize repos from the resolved
`manifest_ref`/`source_context`, then reuse the existing backend pipeline
(`plan_backend` + `DockerBackendProvider.run`) to create a running
instance. Neither the resolver nor the reused pipelines MUST be modified to
support this mode.

#### Scenario: Successful catalog-driven onboarding

- GIVEN a catalog record that resolves uniquely for client identifier
  `acme`
- WHEN `forge onboard acme` runs
- THEN the workspace is materialized from the resolved manifest
  reference/source context
- AND a backend instance is created via the existing `plan_backend` +
  `DockerBackendProvider.run` pipeline
- AND the command exits zero

#### Scenario: Backend failure leaves no orphaned instance

- GIVEN a successful catalog resolution and successful workspace
  materialization
- WHEN `DockerBackendProvider.run` fails while creating the instance
- THEN the command exits non-zero with a single `error:` line
- AND no partially-created instance/resources are left behind (per the
  existing `run` command's rollback contract)

### Requirement: Catalog resolution failures render distinguishable errors

When `ProjectCatalogResolver.resolve()` returns a
`ProjectCatalogResolutionFailure`, `forge onboard <cliente>` MUST render
exactly one `error:` line whose text distinguishes the three failure
classes (`catalog-not-found`, `ambiguous-resolution`, `invalid-catalog`)
and MUST exit non-zero. No workspace materialization or backend creation
MUST be attempted after a resolution failure.

#### Scenario: Catalog record not found

- GIVEN no catalog record matches the supplied client identifier
- WHEN `forge onboard <cliente>` runs
- THEN it prints a single `error:` line identifying the failure as
  catalog-not-found
- AND it exits non-zero without materializing a workspace

#### Scenario: Ambiguous client identifier

- GIVEN more than one catalog record matches the supplied client identifier
- WHEN `forge onboard <cliente>` runs
- THEN it prints a single `error:` line identifying the failure as
  ambiguous-resolution
- AND it exits non-zero without materializing a workspace

#### Scenario: Invalid catalog record

- GIVEN the matched catalog record is invalid or missing a required
  resolved field
- WHEN `forge onboard <cliente>` runs
- THEN it prints a single `error:` line identifying the failure as
  invalid-catalog
- AND it exits non-zero without materializing a workspace

### Requirement: Pass-through-only catalog fields are not actioned this slice

`data_policy_default` and `target_default` from the resolved catalog result
MUST be transported through the catalog-driven `onboard` path but MUST NOT
be acted upon (no data seeding, no remote target selection) in this slice.
The effective target for the created instance MUST remain the existing
local-only backend behavior.

#### Scenario: Resolved defaults are not actioned

- GIVEN a resolved catalog result carrying a non-local `target_default` and
  a `data_policy_default`
- WHEN `forge onboard <cliente>` runs
- THEN the instance is still created via the local `DockerBackendProvider`
- AND no data-seeding or remote-target logic is triggered by either field
