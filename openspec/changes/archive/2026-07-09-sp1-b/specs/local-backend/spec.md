# Delta for local-backend

## ADDED Requirements

### Requirement: Runtime digest override remains ephemeral

The system MUST let `forge run` accept an optional canonical digest-backed Odoo image reference for the local Docker backend. When present, backend planning MUST set `BackendPlan.odoo.image` to that exact digest ref instead of the version tag template. The override MUST exist only for the current runtime invocation and MUST NOT write or require `project.lock`, PublishedLayer/registry-resolution state, or any non-Docker backend integration.

#### Scenario: Canonical digest drives the local backend plan

- GIVEN an operator supplies a canonical digest-backed Odoo image ref to `forge run`
- WHEN the local backend plan is built
- THEN `BackendPlan.odoo.image` equals that supplied digest ref
- AND no persisted lock or registry-resolution state is written

#### Scenario: Missing override falls back to the version template

- GIVEN an operator does not supply a runtime digest override
- WHEN the local backend plan is built
- THEN `BackendPlan.odoo.image` falls back to `odoo-forge-odoo:{odoo_version}`

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
