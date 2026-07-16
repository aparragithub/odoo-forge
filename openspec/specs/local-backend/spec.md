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

### Requirement: plan_backend is a pure core boundary over validated mount-planning input

Backend planning MUST remain a pure core boundary that consumes manifest and instance inputs plus validated evidence-derived mount-planning input. It MUST remain free of I/O and MUST NOT invoke Docker. The design phase owns the concrete function and type signature. Its behavioral contract is to consume manifest data plus a separate, validated mount-planning input produced by the pure core seam; that seam carries mount authority and lock-evidence validation, while `BackendPlan` remains the boundary handed to `BackendProvider`. The planner MUST fail closed when overall evidence is absent, required projected repos are missing, evidence is malformed or incoherent, or any repo commit drifts from `project.lock`. The planner MUST derive mounts only from evidence-backed required/optional roots: required projected repos MUST be present to run; optional/non-required roots MAY be absent; unexpected or incoherent evidence MUST be rejected rather than mounted. The planner MUST NOT create a partial required mount set and MUST NOT use any static or historical fallback. `MaterializedState` is identity/commit evidence only; it does not carry path/root authority.

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

#### Scenario: planned DB env matches the entrypoint contract
- GIVEN the plan is built from complete, lock-consistent evidence
- WHEN `plan_backend` runs
- THEN `plan.odoo.env` and `plan.postgres.env` match the existing entrypoint keys
- AND no `DB_NAME` key is emitted

#### Scenario: valid workspace without promoted overrides runs
- GIVEN the validated planning input includes all lock-required projected repos and no promoted worktrees
- WHEN `plan_backend` runs
- THEN it returns a `BackendPlan`
- AND it includes only the required evidence-backed mounts

#### Scenario: optional roots may be absent
- GIVEN the validated planning input omits a non-required root
- WHEN `plan_backend` runs
- THEN it still returns a `BackendPlan`
- AND the missing optional root is not mounted

#### Scenario: plan wires DB_HOST to the planned Postgres service
- GIVEN a manifest with no external Postgres configured
- WHEN `plan_backend` runs
- THEN `plan.odoo.env["DB_HOST"]` resolves to the planned Postgres alias

#### Scenario: plan models named PG data and Odoo-filestore volumes
- GIVEN a manifest with no external Postgres configured
- WHEN `plan_backend` runs
- THEN `plan.volumes` contains named persistent Postgres-data and Odoo-filestore volumes

#### Scenario: plan is deterministic
- GIVEN the same manifest and validated planning input
- WHEN `plan_backend` runs twice
- THEN both `BackendPlan` results are equal

#### Scenario: complete evidence produces a backend plan
- GIVEN workspace evidence is complete and lock-consistent
- WHEN `plan_backend` runs for `run`
- THEN it returns a `BackendPlan` with the expected evidence-backed mounts
- AND provider methods are not invoked during planning

#### Scenario: missing required projected repo blocks run
- GIVEN a required projected repo is absent from the validated planning input
- WHEN `forge run` starts
- THEN it exits before provider invocation with a single failure cause
- AND no partial required mount set is produced

#### Scenario: malformed or incoherent evidence fails once at the boundary
- GIVEN a scanned path or root/layer pairing is invalid
- WHEN scan/projection materialization runs
- THEN it raises `ScanError` once
- AND the CLI renders one error message with no fallback mount planning

#### Scenario: unexpected evidence is rejected rather than mounted
- GIVEN evidence includes a root or repo not backed by the lock/projection contract
- WHEN `plan_backend` runs
- THEN it rejects that evidence
- AND it does not mount the unexpected root

#### Scenario: commit drift blocks run
- GIVEN evidence is complete but one repo commit differs from `project.lock`
- WHEN `forge run` starts
- THEN it fails before provider invocation
- AND it does not reuse any historical mount fallback

### Requirement: Runtime digest override remains ephemeral

`forge run` MUST accept an optional canonical digest-backed Odoo image reference for the local Docker backend. When present, backend planning MUST set `BackendPlan.odoo.image` to that exact digest ref instead of the version-tag template. The override MUST exist only for the current runtime invocation and MUST NOT write or require `project.lock`, PublishedLayer/registry-resolution state, or any non-Docker backend integration.

#### Scenario: Canonical digest drives the local backend plan
- GIVEN an operator supplies a canonical digest-backed Odoo image ref to `forge run`
- WHEN the local backend plan is built
- THEN `BackendPlan.odoo.image` equals that supplied digest ref
- AND no persisted lock or registry-resolution state is written

#### Scenario: Missing override falls back to the version template
- GIVEN an operator does not supply a runtime digest override
- WHEN the local backend plan is built
- THEN `BackendPlan.odoo.image` falls back to `odoo-forge-odoo:{odoo_version}`

## Capability: postgres-provisioning (New)

### Requirement: run() provisions its own Postgres when none is external

`BackendProvider.run(plan)` MUST create the planned network, Postgres and Odoo
containers, and named Postgres-data and Odoo-filestore volumes when no external
Postgres is configured. It MUST record which resources this invocation created.
Creation of the planned Postgres-data volume by this invocation MUST be the
authority that the database lifecycle is new.

For a new lifecycle, `run` MUST complete a provider-owned Odoo bootstrap that
installs only `base` and exits successfully before it starts the long-running
Odoo server. It MUST NOT bootstrap, repair, or adopt a lifecycle backed by a
pre-existing Postgres-data volume. Bootstrap MUST use the plan's database,
image, network, mounts, filestore, environment, and opaque credentials without
adding a public configuration surface.

After successful bootstrap cleanup, `run` MUST start normal Odoo and poll Docker
`State.Health.Status` monotonically until `healthy` or a bounded provider-owned
deadline expires. Non-healthy states MUST remain recoverable until expiry. The
returned handle MUST represent reachable, Docker-healthy Odoo.

On bootstrap or readiness failure, rollback MUST remove only resources created by
this invocation; reattached volumes MUST remain. Bootstrap failure MUST prevent
normal Odoo startup. The temporary bootstrap container MUST be removed on
success and failure, never preserved for debugging. `stop` MUST preserve named
lifecycle volumes while removing instance containers and network.

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

### Requirement: Local Docker run performs an explicit image pull

The local Docker backend MUST perform an explicit `docker pull` of `BackendPlan.odoo.image` before starting the Odoo container. This pull behavior SHALL apply only to the local Docker runtime path and MUST NOT change status/stop/logs/exec semantics or require pull support from non-Docker backends.

#### Scenario: Pull happens before container start
- GIVEN `BackendPlan.odoo.image` is a canonical digest ref
- WHEN the local Docker backend runs the plan
- THEN `docker pull` executes before the Odoo `docker run`
- AND the started container uses that planned image ref

#### Scenario: Pull scope stays local to Docker run
- GIVEN a non-run backend action or a non-Docker backend
- WHEN the action executes
- THEN no local-Docker pull requirement is imposed

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

`forge run`, `forge status`, `forge stop`, `forge logs`, and `forge exec` MUST call `plan_backend` only where applicable, stop on first failure, and translate adapter errors into a typed taxonomy surfaced as a single-line message and `Exit(1)`. Identity commands MUST remain workspace-independent and MUST NOT scan. `run` MAY scan/materialize workspace evidence, but `status`, `stop`, `logs`, and `exec` MUST use only instance identity and the existing provider calls. `BackendProvider` signatures MUST remain unchanged.

#### Scenario: Docker daemon unavailable fails loud and clean
- GIVEN the Docker daemon is not running
- WHEN `forge run` executes
- THEN it exits non-zero with a single-line `DockerNotAvailable` error

#### Scenario: run fails closed before provider.run
- GIVEN absent, incomplete, or drifted evidence
- WHEN `forge run` executes
- THEN it exits non-zero with a single human-readable error
- AND `BackendProvider.run` is not called

#### Scenario: partial run failure removes only resources this run created
- GIVEN `run()` created the network and data volume but the Odoo container failed
- WHEN the failure occurs
- THEN rollback removes only resources created by this invocation

#### Scenario: reattach-then-fail preserves the existing data volume
- GIVEN a prior `run` left a preserved named data volume and a new `run` re-attaches to it
- WHEN the Odoo container then fails
- THEN rollback does not remove the pre-existing volume

#### Scenario: stop on unknown instance fails loud
- GIVEN an instance id with no matching Docker container
- WHEN `forge stop` runs
- THEN it exits non-zero with a single-line `ContainerNotFound` error

#### Scenario: identity commands stay workspace-independent
- GIVEN no workspace materialization exists
- WHEN `forge status`, `forge stop`, `forge logs`, or `forge exec` runs
- THEN none of them scans the workspace
- AND each command preserves its existing instance-only behavior

#### Scenario: absent instance behavior stays command-specific
- GIVEN an instance whose containers were removed outside `forge`
- WHEN `status()` is called and, separately, `stop`/`logs`/`exec` are called
- THEN `status()` reports not-running without raising
- AND `stop`/`logs`/`exec` exit non-zero with `ContainerNotFound`

#### Scenario: lock, project, and unlock remain unchanged
- GIVEN `forge lock`, `forge project`, or `forge unlock`
- WHEN those commands execute
- THEN their existing behavior is unchanged
- AND this change does not introduce workspace scanning into them

### Requirement: Pull failures surface typed operator diagnostics

The system MUST fail before container start when the explicit pull fails and MUST emit a single-line, operator-readable diagnostic that preserves the failure class. At minimum, tests SHALL distinguish Docker unavailable, image not found, and registry authorization/access denied from generic container-start failures. Raw subprocess traceback MUST NOT reach the terminal.

#### Scenario: Missing image fails cleanly before startup
- GIVEN `docker pull` fails because the image does not exist
- WHEN `forge run` executes with explicit pull
- THEN the command exits non-zero before container start
- AND the operator sees a single-line image-not-found diagnostic

#### Scenario: Authorization failure stays distinct
- GIVEN `docker pull` fails with registry authorization or access denied
- WHEN `forge run` executes with explicit pull
- THEN the command exits non-zero before container start
- AND the operator sees a distinct single-line authorization diagnostic

### Requirement: Real-Docker baseline provides opt-in lifecycle evidence

The integration evidence MUST remain opt-in and MUST validate the canonical local Docker lifecycle without changing production lifecycle, volume, image, credential, or status semantics. The evidence MUST use an isolated project-factory Odoo image and a pinned official PostgreSQL image.

#### Scenario: Prerequisites are unavailable
- GIVEN Docker executable or daemon access is unavailable
- WHEN the explicitly selected integration test starts
- THEN it is skipped with a clear prerequisite reason and no lifecycle failure is reported

#### Scenario: Prerequisites are available
- GIVEN Docker access, the project-factory Odoo image, and the pinned official PostgreSQL image are available
- WHEN the opt-in test executes
- THEN failures after prerequisite detection fail the test rather than being skipped

#### Scenario: Required images and identity are used
- GIVEN an isolated test fixture
- WHEN the lifecycle is provisioned
- THEN Odoo uses the project-factory image, PostgreSQL uses the pinned official image, and every resource has a unique test-owned identity

#### Scenario: Secrets remain safe
- GIVEN credentials are required by the disposable fixture
- WHEN commands, assertions, diagnostics, and verification evidence are produced
- THEN secret values are absent from arguments, logs, output, committed fixtures, and recorded evidence

#### Scenario: Host ports are collision-resistant
- GIVEN the lifecycle is provisioned on a host with unrelated services
- WHEN containers are started
- THEN host ports are allocated ephemerally and the observed mappings are used for assertions

#### Scenario: Readiness is bounded
- GIVEN a cold image boot or a service that never becomes ready
- WHEN lifecycle startup is attempted
- THEN readiness waits are bounded, successful startup proves both database reachability and Odoo health, and timeout failure is reported

#### Scenario: Run, status, and stop complete
- GIVEN startup reaches readiness
- WHEN the test performs `run`, `status`, and `stop`
- THEN `run` returns a reachable instance, `status` reports its live running state, and `stop` completes successfully

#### Scenario: Stop preserves lifecycle volumes
- GIVEN the test-owned instance has named lifecycle volumes
- WHEN `stop` removes the instance
- THEN the named lifecycle volumes remain present, while containers and the lifecycle network are absent

#### Scenario: Cleanup is ownership-scoped
- GIVEN setup succeeds, partially succeeds, or fails
- WHEN final test cleanup runs
- THEN cleanup is unconditional, deletes only uniquely test-owned disposable resources, and never deletes pre-existing or unrelated resources

#### Scenario: Residual checks are independent
- GIVEN lifecycle execution or cleanup reports an error
- WHEN residual checks run
- THEN independent label/name-based checks identify any remaining test-owned containers, networks, or disposable resources without treating preserved lifecycle volumes as leaks

#### Scenario: The default suite remains daemon-independent
- GIVEN the repository's default test command is executed
- WHEN tests are collected and run
- THEN this integration evidence is excluded; an explicit integration command is required to exercise Docker

#### Scenario: Verification records evidence
- GIVEN the baseline test has been exercised
- WHEN verification is completed
- THEN the receipt records Docker client/server versions, exact commands and results, readiness outcome, stop-preservation result, cleanup result, and residual checks

#### Scenario: Production defects are extracted
- GIVEN the real-Docker evidence exposes a defect in production behavior
- WHEN verification classifies the finding
- THEN this change fails or stops without masking the defect, and the defect is recorded as a separate SDD change rather than changing production code here

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
