# Spec: Local Docker Backend (Phase 2, Slice 4b)

## Purpose

First `BackendProvider` implementation (design §2.4): turns a Slice-3
`MaterializedState` into a live, introspectable Odoo instance on Docker,
with its own provisioned Postgres. Pure core plans; a subprocess adapter
executes.

## Capability: backend-provider-port (New)

### Requirement: BackendProvider is a Protocol covering run/status/stop/logs/exec

`ports/backend_provider.py` MUST define a `Protocol` with the following FINAL
signatures (reconciled with design): `run(plan) -> InstanceRef` (returns a
handle to a ready, reachable instance), `status(ref) -> InstanceStatus`,
`stop(ref) -> None`, `logs(ref, role) -> str` (the `role` selects the Odoo or
Postgres container; returns the log text as a `str`), `exec(ref, argv) ->
ExecResult` (carries `exit_code`, `stdout`, `stderr`). `backup`/`restore` MUST
NOT be part of this port (Non-goals). `odoo_forge` MUST depend only on this
interface; no adapter lives in core.

#### Scenario: import-linter enforces purity
- GIVEN the 5-contract import-linter config
- WHEN CI runs `lint-imports`
- THEN `odoo_forge` imports zero `docker`/`subprocess` symbols and never
  imports the backend adapter package

#### Scenario: Adapter satisfies the port structurally
- GIVEN an instance of the concrete Docker adapter
- WHEN checked against `isinstance(adapter, BackendProvider)`
- THEN the check succeeds with no explicit inheritance from the port

#### Scenario: Adapter matches the port signatures, not just method names
- GIVEN `BackendProvider` is `runtime_checkable` (isinstance verifies method
  NAMES only, not parameter lists or return types)
- WHEN an explicit signature-conformance test compares each adapter method's
  signature against the port
- THEN every method's parameters and return type match the port's declared
  signature

## Capability: backend-planner (New)

### Requirement: plan_backend is a pure function over manifest + MaterializedState

A pure `plan_backend(manifest, state, instance="default") -> BackendPlan` MUST
live in `odoo_forge` with zero I/O and compute: container/network topology, a
named persistent Postgres data volume AND a named persistent Odoo-filestore
volume (`plan.volumes`), one mount per Slice-3 root (`community`, `enterprise`,
`localization`, `custom`, `worktrees`), the DB env vars that
`factory/entrypoint.sh:143-159` ACTUALLY consumes, and identifying labels. It
MUST NOT invoke `docker` or any adapter.

`BackendPlan` carries env and mounts PER container (`plan.postgres` /
`plan.odoo`, each a `ContainerSpec` with its own `env`/`mounts`), not as
top-level fields; this is the shape reconciled with the design (design
"Interfaces / Contracts"). There is no top-level `BackendPlan.env` or
`BackendPlan.mounts`.

The env plan is the single source of truth for both containers and MUST match
the entrypoint exactly (verified against `factory/entrypoint.sh:143-159`):
- **Odoo container**: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and
  `POSTGRES_DB`. The entrypoint reads `POSTGRES_DB` (default `postgres`) as the
  `--database` selector — it does NOT read `DB_NAME`. Planning `DB_NAME` is a
  no-op that leaves Odoo booting the `postgres` maintenance database, so
  `DB_NAME` MUST NOT be emitted.
- **Postgres container**: `POSTGRES_PASSWORD`, `POSTGRES_USER`, `POSTGRES_DB`.
  The stock `postgres` image exits on boot without `POSTGRES_PASSWORD`, so the
  planner MUST provide the Postgres-side credentials, not only the Odoo-side
  connection env.
- The Odoo `DB_USER`/`DB_PASSWORD`/`POSTGRES_DB` MUST equal the Postgres
  `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`. Credential source:
  deterministic local-dev defaults `odoo`/`odoo`, with the project database name
  derived from the sanitized `manifest.name`.

#### Scenario: Planned DB env matches what the entrypoint consumes
- GIVEN the entrypoint at `factory/entrypoint.sh:143-159` reads `DB_HOST`,
  `DB_PORT`, `DB_USER`, `DB_PASSWORD` and `POSTGRES_DB` (never `DB_NAME`)
- WHEN `plan_backend` runs
- THEN `plan.odoo.env` keys are exactly `{DB_HOST, DB_PORT, DB_USER,
  DB_PASSWORD, POSTGRES_DB}`, `plan.postgres.env` keys are exactly
  `{POSTGRES_PASSWORD, POSTGRES_USER, POSTGRES_DB}`, no `DB_NAME` key is present,
  and the shared user/password/db values are equal across the two containers

#### Scenario: Plan includes all five mount roots
- GIVEN a `MaterializedState` with repos under all five mount roots
- WHEN `plan_backend` runs
- THEN `plan.odoo.mounts` has exactly one entry per root

#### Scenario: Plan wires DB_HOST to the planned Postgres service
- GIVEN a manifest with no external Postgres configured
- WHEN `plan_backend` runs
- THEN `plan.odoo.env["DB_HOST"]` resolves to the planned Postgres
  container's network alias, not a literal `localhost`

#### Scenario: Plan models named PG data and Odoo-filestore volumes
- GIVEN a manifest with no external Postgres configured
- WHEN `plan_backend` runs
- THEN `plan.volumes` contains a named persistent Postgres data volume AND a
  named persistent Odoo-filestore volume (`/var/lib/odoo`), and the Odoo
  filestore volume is mounted on `plan.odoo`

#### Scenario: Plan is deterministic
- GIVEN the same manifest and materialized state
- WHEN `plan_backend` runs twice
- THEN both `BackendPlan` results are equal

## Capability: postgres-provisioning (New)

### Requirement: run() provisions its own Postgres when none is external

`BackendProvider.run(plan)` MUST create a Postgres container (with its
`POSTGRES_PASSWORD`/`POSTGRES_USER`/`POSTGRES_DB` supplied so the stock image
does not exit on boot), a named persistent Postgres data volume, a named
persistent Odoo-filestore volume (`/var/lib/odoo`), and a Docker network joining
Postgres to the Odoo container when no external Postgres is configured,
satisfying `factory/entrypoint.sh:143-159`'s hard requirement for a reachable
database. Before returning, `run` MUST gate Postgres TCP readiness and then wait
for the Odoo container's health to reach `healthy`, using a configurable timeout
whose default floor is the image HEALTHCHECK start-period plus at least one
interval plus a cold-first-boot margin (`Dockerfile:100`: `--start-period=60s
--interval=30s`), for a recommended default of at least 180s, so a healthy but
slow cold boot is not spuriously failed as `ContainerRunError`. The returned handle is thus reachable and not merely
created. Backup/restore of that data MUST NOT be implemented in this slice.

`run` MUST record, per resource, whether THIS invocation created it (existence
checked before create; `docker volume create` is idempotent against a preserved
named volume). Rollback on failure MUST tear down ONLY resources this invocation
created; a re-attached, pre-existing named volume MUST NEVER be removed. `stop`
uses `docker rm -f -v` on the containers: named volumes are immune to `-v`, so
the named PG and filestore volumes are preserved while stray anonymous volumes
are reaped.

#### Scenario: run() with no external Postgres yields a working instance
- GIVEN a materialized workspace and a manifest with no external Postgres
- WHEN `run(plan)` executes
- THEN a Postgres container (with `POSTGRES_PASSWORD` set), a named Postgres
  data volume, a named Odoo-filestore volume, and a network are created, the
  Odoo container joins that network, and the returned `InstanceRef` reflects a
  running, reachable Odoo container (its health has reached `healthy`)

## Capability: label-based-status (New)

### Requirement: status() derives state from Docker, never a parallel registry

`BackendProvider.status(instance)` MUST derive `InstanceStatus` exclusively
from Docker introspection (labels set at `run()` time plus `docker
inspect`), per design §6.2. No file, database, or in-process registry of
running instances MUST be persisted or consulted.

#### Scenario: Status reflects live Docker state
- GIVEN an instance previously created by `run()`
- WHEN `status(instance)` is called
- THEN the reported state is read from Docker inspect/labels, not from any
  stored registry

#### Scenario: Manually-removed container reflects as not-running
- GIVEN an instance whose container was removed outside `forge` (e.g.
  `docker rm`)
- WHEN `status(instance)` is called
- THEN it reports not-running, with no error from a stale registry entry —
  because there is no registry to go stale

## Capability: forge-backend-cli (New)

### Requirement: run/status/stop/logs/exec commands enforce a resilient boundary

`forge run`, `forge status`, `forge stop`, `forge logs`, `forge exec` MUST
call `plan_backend` (where applicable) and the injected `BackendProvider`,
stop on first failure, and translate adapter errors into a typed taxonomy —
at minimum `DockerNotAvailable`, `ImageNotFound`, `ContainerNotFound` —
surfaced as a single-line message and `Exit(1)`. No raw subprocess/Docker
traceback MUST reach the terminal.

`PortConflict` is INTENTIONALLY NOT part of this taxonomy: the design DECIDES an
ephemeral host-port strategy (`-p 0:8069`/`-p 0:8072`, mapped port reported by
`status()`), under which host-port collisions are structurally unreachable. This
supersedes the earlier "at minimum ... `PortConflict`" requirement; the design
records the same decision so the two documents stay consistent.

`DockerNotAvailable` MUST be raised for BOTH a missing `docker` binary (subprocess
`FileNotFoundError`) and an unreachable daemon (binary present, non-zero exit with
a `Cannot connect to the Docker daemon` stderr marker) — a missing binary is not
the only way Docker can be unavailable.

#### Scenario: Docker daemon unavailable fails loud and clean
- GIVEN the Docker daemon is not running (binary present, `Cannot connect to
  the Docker daemon` on stderr)
- WHEN `forge run` executes
- THEN it exits non-zero with a single-line `DockerNotAvailable` error

#### Scenario: Partial run() failure removes only resources this run created
- GIVEN a FIRST `run()` created the Postgres container, network and data volume
  but the Odoo container failed to become healthy (`ContainerRunError`)
- WHEN the failure occurs
- THEN rollback removes ONLY the resources this run created — the
  partially-created containers, network AND the volumes created by this run
  (`docker rm -f -v` for created containers, `docker volume rm` for created
  volumes, `docker network rm`) — before exiting non-zero with a single-cause
  error

#### Scenario: Reattach-then-fail preserves the existing data volume
- GIVEN a prior `run` -> `stop` left a preserved named Postgres data volume (and
  Odoo-filestore volume), and a new `run` re-attaches to that volume but then the
  Odoo container fails to become healthy (`ContainerRunError`)
- WHEN rollback runs
- THEN rollback removes only the resources THIS invocation created and MUST NOT
  run `docker volume rm` against the re-attached, pre-existing PG/filestore
  volume — the preserved database and filestore survive the failed re-run

#### Scenario: stop() on unknown instance fails loud
- GIVEN an instance id with no matching Docker container
- WHEN `forge stop` runs
- THEN it exits non-zero with a single-line `ContainerNotFound` error

#### Scenario: status() vs stop/logs/exec on an absent instance diverge
- GIVEN an instance whose containers were removed outside `forge`
- WHEN `status()` is called AND, separately, `stop`/`logs`/`exec` are called
- THEN `status()` reports not-running WITHOUT raising, while
  `stop`/`logs`/`exec` exit non-zero with a single-line `ContainerNotFound`
  error

## Non-goals

- **4a registry resolution** (`PublishedLayer`/`registry://`,
  `locking.py:27-29`) — out of scope, tracked separately.
- **backup/restore** — design §5 buckets this to Phase 4.
- **Seeding/anonymization** (§4.3, §9.5) — extension point only, no
  implementation here.

## Deferred to Design

- Container/network/label naming schema (collision-safe across hosts).
- Concrete readiness signal for `status()` (`HEALTHCHECK` state vs port
  probe vs log pattern).
- Scope of a `doctor` command for Docker-availability prerequisites.
