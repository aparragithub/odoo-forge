# Delta for manifest

## ADDED Requirements

### Requirement: Host mount base resolves at the CLI composition root

The CLI composition root MUST resolve a single HOST mount base `Path` via,
in order: `FORGE_MOUNT_BASE` env → else
`${XDG_STATE_HOME:-~/.local/state} / "odoo-forge"`. Default HOST base MUST
be `~/.local/state/odoo-forge`; `/mnt` MUST NOT be the default. The
CONTAINER mount base MUST stay the fixed constant `/mnt`, independent of the
HOST base. `odoo_forge` core MUST NOT read environment variables;
resolution happens only in `odoo_forge_cli`.

#### Scenario: Default resolution with no env vars set
- GIVEN neither `FORGE_MOUNT_BASE` nor `XDG_STATE_HOME` is set
- WHEN the CLI resolves the host mount base
- THEN it resolves to `~/.local/state/odoo-forge`

#### Scenario: FORGE_MOUNT_BASE overrides everything
- GIVEN `FORGE_MOUNT_BASE=/custom/path`, regardless of `XDG_STATE_HOME`
- WHEN the CLI resolves the host mount base
- THEN it resolves to `/custom/path`

#### Scenario: XDG_STATE_HOME influences the default
- GIVEN `FORGE_MOUNT_BASE` is unset and `XDG_STATE_HOME=/xdg/state`
- WHEN the CLI resolves the host mount base
- THEN it resolves to `/xdg/state/odoo-forge`

#### Scenario: Backward compatibility via explicit override
- GIVEN `FORGE_MOUNT_BASE=/mnt`
- WHEN the CLI resolves the host base and derives host roots
- THEN host checkout/scan/unlock paths match the pre-change hardcoded
  `/mnt/*` behavior exactly

#### Scenario: Relative FORGE_MOUNT_BASE is rejected with a clear error
- GIVEN `FORGE_MOUNT_BASE` is set to a non-absolute path
- WHEN the CLI resolves the host base
- THEN it fails fast with a clear error stating the base must be absolute,
  never letting a relative source token reach the Docker bind mount (where
  Docker would silently treat it as a named volume)

#### Scenario: Non-absolute XDG_STATE_HOME is ignored
- GIVEN `FORGE_MOUNT_BASE` is unset and `XDG_STATE_HOME` is a non-absolute path
- WHEN the CLI resolves the host base
- THEN the non-absolute `XDG_STATE_HOME` is ignored per the XDG Base Directory
  spec and the default `~/.local/state/odoo-forge` base is used

### Requirement: Host and container mount root tables are decoupled

The five mount roots (`community`, `custom`, `localization`, `enterprise`,
`worktrees`) MUST derive as `<base>/<root>` from any base. The CLI MUST
build two independent tables from the same five keys: a HOST table rooted
at the resolved host mount base (used for `WorkspaceProvider`
checkout/scan/promote and `MaterializedState` path evidence), and a
CONTAINER table rooted at the fixed `/mnt` constant (used for
`MountEvidence.container_path` and Docker bind-mount targets). Changing the
HOST base MUST NOT change any CONTAINER-side path.

#### Scenario: Container path is unaffected by a custom host base
- GIVEN the host mount base resolves to `/custom/path`
- WHEN a bind mount is computed for the `custom` root
- THEN the host side is `/custom/path/custom/...` and the container side is
  `/mnt/custom/...`

#### Scenario: Default host base still yields fixed container paths
- GIVEN the host mount base resolves to `~/.local/state/odoo-forge`
- WHEN a bind mount is computed for any root
- THEN the container side is `/mnt/<root>/...`, unchanged from prior behavior

## MODIFIED Requirements

### Requirement: forge validate delegates all logic to the core

`forge validate [--manifest project.yaml]` MUST parse and validate the
manifest, run `compose()`, and report drift when a `project.lock` exists.
When a workspace tree exists under the resolved HOST mount base, it MUST
call `WorkspaceProvider.scan`, derive `MaterializedState` via
`materialize_state`, and pass it into `detect_drift` instead of `None`. All
decision logic MUST live in `odoo_forge`; the CLI only orchestrates.
(Previously: mount roots were fixed at `/mnt/*`.)

#### Scenario: Malformed manifest reports a clear error
- GIVEN an invalid `project.yaml`
- WHEN `forge validate` runs
- THEN it exits non-zero with a single-cause, human-readable error

#### Scenario: Rootless validate under the default host base
- GIVEN no `FORGE_MOUNT_BASE` override and a workspace materialized under
  `~/.local/state/odoo-forge`
- WHEN `forge validate` runs as a non-root user
- THEN it scans and reports drift without requiring elevated permissions

### Requirement: forge project executes the plan through a resilient boundary

`forge project [--manifest][--lock]` MUST load the manifest and lock, call
`plan_projection`, then execute each step via `WorkspaceProvider.checkout`
against the resolved HOST mount roots. Each checkout MUST be atomic
(clone-to-temp then rename). On a step failure the command MUST stop, MUST
NOT touch completed steps, and MUST exit non-zero with a single-cause error.
(Previously: checkout always targeted the hardcoded `/mnt/*` roots.)

#### Scenario: Valid lock projects every layer under the resolved host base
- GIVEN a valid `project.lock` and no `FORGE_MOUNT_BASE` override
- WHEN `forge project` runs
- THEN every locked repo is checked out under
  `~/.local/state/odoo-forge/<root>`, rootless

#### Scenario: Mid-plan checkout failure stops cleanly
- GIVEN a plan where the third step's remote is unreachable
- WHEN `forge project` runs
- THEN steps 1–2 remain checked out, step 3 leaves no half-cloned directory

### Requirement: forge unlock promotes a targeted repo

`forge unlock --layer NAME --repo URL` MUST call `unlock`, which computes
`source`/`dest`/`branch` against the resolved HOST `worktrees` root and
invokes `WorkspaceProvider.promote(source, dest, branch)`, then report the
branch name, or exit non-zero on `AlreadyUnlockedError`/`ScanError`.
(Previously: `dest` was always computed under the hardcoded
`/mnt/worktrees/<layer>/`.)

#### Scenario: Unlock succeeds under the resolved host base
- GIVEN a read-only materialized repo and no `FORGE_MOUNT_BASE` override
- WHEN `forge unlock --layer core --repo <url>` runs
- THEN `promote` is called with `dest` under
  `~/.local/state/odoo-forge/worktrees/`, and the command exits zero
