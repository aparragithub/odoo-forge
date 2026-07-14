# Delta for Local Docker Backend

## MODIFIED Requirements

### Requirement: run() provisions its own Postgres when none is external

`BackendProvider.run(plan)` MUST create the planned network, Postgres and Odoo containers, and named Postgres-data and Odoo-filestore volumes when no external Postgres is configured. It MUST record which resources this invocation created. Creation of the planned Postgres-data volume by this invocation MUST be the authority that the database lifecycle is new.

For a new lifecycle, `run` MUST complete a provider-owned Odoo bootstrap that installs only `base` and exits successfully before it starts the long-running Odoo server. It MUST NOT bootstrap, repair, or adopt a lifecycle backed by a pre-existing Postgres-data volume. Bootstrap MUST use the plan's database, image, network, mounts, filestore, environment, and opaque credentials without adding a public configuration surface.

After successful bootstrap cleanup, `run` MUST start normal Odoo and poll Docker `State.Health.Status` monotonically until `healthy` or a bounded provider-owned deadline expires. Non-healthy states MUST remain recoverable until expiry. The returned handle MUST represent reachable, Docker-healthy Odoo.

On bootstrap or readiness failure, rollback MUST remove only resources created by this invocation; reattached volumes MUST remain. Bootstrap failure MUST prevent normal Odoo startup. The temporary bootstrap container MUST be removed on success and failure, never preserved for debugging. `stop` MUST preserve named lifecycle volumes while removing instance containers and network.

(Previously: `run` started normal Odoo immediately after Postgres TCP readiness and relied on Docker-health polling without initializing a fresh database schema.)

#### Scenario: new lifecycle bootstraps before normal Odoo
- GIVEN this invocation creates the planned Postgres-data volume
- WHEN `run(plan)` provisions the backend
- THEN `base` bootstrap succeeds and its temporary container is removed before normal Odoo starts
- AND `run` returns only after normal Odoo becomes Docker-healthy

#### Scenario: existing lifecycle is not repaired
- GIVEN the planned Postgres-data volume already exists
- WHEN `run(plan)` attaches that lifecycle
- THEN no bootstrap command runs, even if the database is incomplete

#### Scenario: bootstrap failure rolls back owned resources
- GIVEN this invocation created a new database lifecycle and bootstrap exits unsuccessfully
- WHEN `run(plan)` fails
- THEN normal Odoo is never started, the temporary container is removed, and only invocation-created resources are rolled back

#### Scenario: bootstrap identity collision fails safely
- GIVEN the derived temporary bootstrap container name already exists
- WHEN `run(plan)` performs preflight checks
- THEN it fails before provisioning and does not adopt, remove, or replace that container

#### Scenario: unhealthy normal server recovers before deadline
- GIVEN bootstrap succeeded and normal Odoo changes from `unhealthy` to `healthy`
- WHEN polling remains within the bounded deadline
- THEN `run(plan)` continues polling and succeeds

## ADDED Requirements

### Requirement: Bootstrap and readiness diagnostics are secret-safe

Bootstrap and readiness failures MUST capture bounded diagnostics before cleanup, MUST redact resolved credentials and non-empty planned environment values, and MUST preserve the primary failure and cleanup-incomplete details. Readiness timeout diagnostics MUST include final health, selected inspect fields, and bounded Odoo logs. No diagnostic failure MAY broaden cleanup ownership.

#### Scenario: bootstrap failure reports safe evidence
- GIVEN bootstrap output contains credentials or planned environment values
- WHEN bootstrap exits unsuccessfully
- THEN the error identifies bootstrap failure without exposing those values and cleanup still runs

#### Scenario: readiness timeout retains completed defenses
- GIVEN bootstrap succeeded but normal Odoo never becomes healthy
- WHEN the provider deadline expires
- THEN selected final health and bounded redacted logs are reported before created-only rollback

### Requirement: Factory, ownership, and acceptance contracts remain unchanged

This change MUST NOT modify factory behavior, the baseline harness, public configuration, lifecycle-volume ownership, or secret injection contracts. Acceptance MUST use unchanged real-Docker baseline and factory smoke harnesses.

#### Scenario: unchanged harness proves the lifecycle
- GIVEN Docker prerequisites are available
- WHEN the baseline executes `run -> status -> stop`
- THEN fresh bootstrap precedes healthy normal Odoo, lifecycle volumes survive until final cleanup, and no owned residual remains
