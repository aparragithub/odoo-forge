# Delta for local-backend

## MODIFIED Requirements

### Requirement: plan_backend is a pure core boundary over validated mount-planning input

Backend planning MUST remain a pure core boundary that consumes manifest and instance inputs plus validated evidence-derived mount-planning input. It MUST remain free of I/O and MUST NOT invoke Docker. The design phase owns the concrete function and type signature. Its behavioral contract is to consume manifest data plus a separate, validated mount-planning input produced by the pure core seam; that seam carries mount authority and lock-evidence validation, while `BackendPlan` remains the boundary handed to `BackendProvider`. The planner MUST fail closed when overall evidence is absent, required projected repos are missing, evidence is malformed or incoherent, or any repo commit drifts from `project.lock`. The planner MUST derive mounts only from evidence-backed required/optional roots: required projected repos MUST be present to run; optional/non-required roots MAY be absent; unexpected or incoherent evidence MUST be rejected rather than mounted. The planner MUST NOT create a partial required mount set and MUST NOT use any static or historical fallback. `MaterializedState` is identity/commit evidence only; it does not carry path/root authority.

(Previously: mounts came from `MaterializedState` plus static roots, without an explicit seam for validated mount evidence or conditional roots.)

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

### Requirement: run/status/stop/logs/exec commands enforce a resilient boundary

`forge run`, `forge status`, `forge stop`, `forge logs`, and `forge exec` MUST call `plan_backend` only where applicable, stop on first failure, and translate adapter errors into a typed taxonomy surfaced as a single-line message and `Exit(1)`. Identity commands MUST remain workspace-independent and MUST NOT scan. `run` MAY scan/materialize workspace evidence, but `status`, `stop`, `logs`, and `exec` MUST use only instance identity and the existing provider calls. `BackendProvider` signatures MUST remain unchanged.

(Previously: identity commands were not explicitly guarded against scanning, and the boundary did not state the unchanged port contract.)

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
