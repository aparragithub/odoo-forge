# Delta for manifest

## MODIFIED Requirements

### Requirement: materialize_state is a pure core function over raw scan results

A pure `materialize_state(scanned: list[ScannedRepo], roots) -> MaterializedState` MUST derive each repo's layer name from `/mnt/<root>/<layer>/...` path evidence, group repos by layer, and perform zero I/O. It MUST raise `ScanError` for malformed or incoherent scan/projection evidence, and it MUST not invent mount placement or historical fallback. `MaterializedState` MUST remain identity/commit evidence only; path/root authority belongs to the separate planning view used by backend planning. Missing directories MAY materialize as partial evidence, and that partial state still remains identity/commit evidence only.

(Previously: malformed paths were rejected, but the requirement did not explicitly keep mount authority out of `MaterializedState` or cover the no-fallback rule.)

#### Scenario: fully projected tree materializes clean
- GIVEN `scan` returned one `ScannedRepo` per planned repo under its mount root
- WHEN `materialize_state(scanned, roots)` runs
- THEN the resulting `MaterializedState` preserves the lock's repo identities and commits
- AND `detect_drift(..., materialized=state)` reports `is_clean = True`

#### Scenario: missing directory is partial evidence, not a scan error
- GIVEN `scan` returned no entry for one planned layer's directory
- WHEN `materialize_state` runs
- THEN it completes without raising
- AND the returned state can still be used as partial identity/commit evidence

#### Scenario: missing directory still reports drift downstream
- GIVEN `materialize_state` returned partial evidence
- WHEN `detect_drift(..., materialized=state)` runs
- THEN the missing repo is reported as `not_materialized`

#### Scenario: malformed or incoherent scanned evidence fails loud
- GIVEN a `ScannedRepo` whose path does not match `/mnt/<root>/<layer>/...`
- WHEN `materialize_state` runs
- THEN it raises `ScanError` naming the offending path

#### Scenario: impossible root/layer pairing fails loud
- GIVEN scan evidence that names a root/layer combination that cannot exist
- WHEN `materialize_state` runs
- THEN it raises `ScanError` once

### Requirement: forge validate delegates all logic to the core

`forge validate [--manifest project.yaml]` MUST parse and validate the manifest, run `compose()`, and report drift when a `project.lock` exists. When a workspace tree exists under the fixed mount roots, it MUST call `WorkspaceProvider.scan` for raw `ScannedRepo` facts, derive `MaterializedState` via the pure core `materialize_state`, and pass it into `detect_drift`. All decision logic MUST live in `odoo_forge`; the CLI only orchestrates and prints single-cause errors.

(Previously: workspace evidence errors were not explicitly required to render once at the CLI boundary.)

#### Scenario: malformed manifest reports a clear error
- GIVEN an invalid `project.yaml`
- WHEN `forge validate` runs
- THEN it exits non-zero with a single-cause, human-readable error

#### Scenario: malformed workspace evidence is rendered once
- GIVEN scan/projection materialization raises `ScanError`
- WHEN `forge validate` runs
- THEN the CLI emits one error message
- AND it does not re-raise or duplicate the boundary failure

#### Scenario: commit drift is reported from real workspace evidence
- GIVEN a lock and a workspace where one repo is checked out at a stale commit
- WHEN `forge validate` runs
- THEN it reports `commit_mismatch` drift for that repo

#### Scenario: unchanged lock and workspace remain clean
- GIVEN a lock whose `generated_from` matches the manifest hash and state matching lock-declared commits
- WHEN `forge validate` runs
- THEN `detect_drift` remains clean
