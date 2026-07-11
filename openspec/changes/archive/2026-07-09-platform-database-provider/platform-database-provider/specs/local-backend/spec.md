# Delta for Local Docker Backend

## MODIFIED Requirements

### Requirement: run() provisions its own Postgres when none is external

`BackendProvider.run(plan)` MUST consume a database reference supplied by the database-provider lifecycle and MUST NOT provision or own PostgreSQL resources. It MUST gate database reachability and wait for Odoo health `healthy` before returning, with a configurable timeout whose default floor remains at least 180 seconds. It MUST record resources it creates and, on failure, remove only those resources; pre-existing named volumes and all database-provider resources MUST be preserved.

(Previously: `run()` provisioned and owned the local PostgreSQL container and its data volume.)

#### Scenario: run() uses the supplied database

- GIVEN a reachable database reference and a materialized workspace
- WHEN `run(plan)` executes
- THEN it starts a reachable healthy Odoo instance without provisioning PostgreSQL

#### Scenario: Database is unreachable

- GIVEN a supplied database reference is unreachable
- WHEN `run(plan)` executes
- THEN it fails without creating PostgreSQL resources

#### Scenario: Failed run preserves provider and existing volumes

- GIVEN a failed run re-attaches to a pre-existing named filestore volume
- WHEN rollback runs
- THEN it removes only resources created by that run and preserves that volume and database-provider resources

### Requirement: run/status/stop/logs/exec commands enforce a resilient boundary

`forge run`, `forge status`, `forge stop`, `forge logs`, and `forge exec` MUST call `plan_backend` where applicable and the injected `BackendProvider`, stop on first failure, and translate adapter errors into a typed taxonomy including `DockerNotAvailable`, `ImageNotFound`, and `ContainerNotFound`, as a single-line message and `Exit(1)`. Raw Docker or subprocess tracebacks MUST NOT reach the terminal. `forge run` MUST use the supplied database-provider reference, preserve provider resources, and roll back only local resources it created. `PortConflict` MUST NOT be required because host ports are ephemeral. `DockerNotAvailable` MUST cover a missing binary and an unreachable daemon.

(Previously: commands also owned PostgreSQL provisioning and described rollback of local PostgreSQL resources.)

#### Scenario: Docker daemon unavailable fails loud and clean

- GIVEN the Docker daemon is unavailable
- WHEN `forge run` executes
- THEN it exits non-zero with a single-line `DockerNotAvailable` error

#### Scenario: Partial run failure removes only local resources

- GIVEN `run()` created local Odoo resources but health fails
- WHEN rollback runs
- THEN it removes only those local resources and exits non-zero with one typed error

#### Scenario: Reattach-then-fail preserves existing resources

- GIVEN a prior run left a named filestore volume and a supplied database reference
- WHEN a later run fails health checks
- THEN rollback preserves that volume and all database-provider resources

#### Scenario: stop() on unknown instance fails loud

- GIVEN an instance id with no matching Docker container
- WHEN `forge stop` runs
- THEN it exits non-zero with a single-line `ContainerNotFound` error

#### Scenario: status differs from unavailable operational commands

- GIVEN an instance was removed outside `forge`
- WHEN `status()` and, separately, `stop`, `logs`, or `exec` run
- THEN status reports not-running while the operational command returns `ContainerNotFound`
