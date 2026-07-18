# Exploration: Configurable mount base (`/mnt` → env-driven)

## Current State

`MOUNT_ROOTS: dict[str, Path]` is a module-level constant in
`src/odoo_forge/manifest/projection.py:33-39`, pinning
`community/custom/localization/enterprise/worktrees` under `/mnt/*`.
`MountRoot` (Literal type) is defined just above it at line 31.

Verified via `codegraph_explore` + targeted reads (no guessing):

- **CLI explicit references (5, confirmed)**: `src/odoo_forge_cli/main.py`
  imports `MOUNT_ROOTS` at line 39; uses it at lines 252, 253 (`validate`
  command: `provider.scan(list(MOUNT_ROOTS.values()))`,
  `materialize_state(scanned, MOUNT_ROOTS)`) and 443, 444, 450 (`run` command:
  same scan/materialize pattern, plus `build_mount_planning_view(..., MOUNT_ROOTS)`).
- **Hidden asymmetry (the real gap)**: `materialize_state` (projection.py:203)
  and `build_mount_planning_view` (projection.py:252) already accept
  `roots: Mapping[str, Path]` as an explicit parameter — they are already
  injectable/pure. But `plan_projection` (projection.py:106, used at line 136:
  `MOUNT_ROOTS[mount_root]`) and `plan_unlock` (projection.py:143, used at
  lines 185-186: `MOUNT_ROOTS[mount_root]` / `MOUNT_ROOTS["worktrees"]`) read
  the **module-level global directly**, despite both docstrings claiming
  "pure, zero I/O." `main.py`'s `project` command (lines 350-351) and `unlock`
  command (lines 387-388) call these two functions without ever mentioning
  `MOUNT_ROOTS` — the global leaks in transitively. Any fix that only touches
  the "5 CLI call sites" misses this.
- **XDG precedent**: `src/odoo_forge_postgres_docker/provider.py:481-489`,
  `_default_authority()` static method:
  `Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "odoo-forge" / "postgres-docker"`.
  It is called lazily at instantiation time
  (`self._ownership_authority = ownership_authority or self._default_authority()`
  at line 157) inside the **adapter package**, not core, not CLI — and it's
  injectable via constructor parameter.
- **Import-linter contracts** (`pyproject.toml` lines 76-119): core
  (`odoo_forge`) is forbidden from importing `docker, boto3, kubernetes, git,
  typer, subprocess, requests, httpx` and the
  `odoo_forge_cli/_git/_workspace/_docker/_registry` adapter packages. Notably
  `os` is **not** forbidden — a naive `os.environ.get(...)` at core module
  import time would pass import-linter but would silently violate the "pure,
  zero I/O" docstring guarantee and break test determinism.
- **Composition-root pattern already established**:
  `_make_workspace_provider()` / `_make_backend_provider()` / `_make_provider()`
  in `main.py` (lines 60-79), each commented
  `"""Composition root: the ONE place the concrete X adapter is built."""` —
  the natural place to add an analogous `_resolve_mount_base()` seam.
- **Test surface** (grep `tests/` for `/mnt`/`MOUNT_ROOTS`, 10 files):
  `tests/manifest/test_projection.py`,
  `tests/manifest/test_projection_roundtrip.py`, `tests/cli/test_unlock.py`,
  `tests/cli/test_lock.py`, `tests/cli/test_validate.py`,
  `tests/cli/test_backend.py`, `tests/backend/test_plan.py`,
  `tests/ports/test_workspace_provider.py`,
  `tests/adapters/test_docker_provider.py`,
  `tests/adapters/test_workspace_provider.py`. Most assert literal `/mnt/...`
  `Path` values; `test_projection.py` and `test_projection_roundtrip.py` import
  `MOUNT_ROOTS` directly and pass it explicitly to
  `materialize_state`/`build_mount_planning_view`. Critically, **no test today
  passes a `roots` argument to `plan_projection`/`plan_unlock`** — they rely
  entirely on the global.

## Affected Areas

- `src/odoo_forge/manifest/projection.py` — `MOUNT_ROOTS` constant (line 33),
  `plan_projection` (line 106, needs a `roots` param), `plan_unlock` (line 143,
  needs a `roots` param)
- `src/odoo_forge_cli/main.py` — composition root; needs new
  `_resolve_mount_base()` / `_build_mount_roots()` functions near lines 60-79,
  and threading the resolved roots through `validate` (252-253), `project`
  (350-351), `unlock` (387-388), `run` (443-450)
- `src/odoo_forge_postgres_docker/provider.py:481-489` — pattern to mirror (not
  to modify)
- 10 test files listed above — the affected test surface for the next phase to
  scope

## Approaches

1. **Env read at core module-import time**
   (`MOUNT_ROOTS = {... Path(os.environ.get("FORGE_MOUNT_BASE", ...)) ...}`
   directly in `projection.py`)
   - Pros: minimal diff, no signature changes, no test breakage for path values
     (base changes but structure doesn't)
   - Cons: violates "pure, zero I/O" core contract in spirit; makes core
     behavior depend on process environment/import order; complicates test
     isolation (env leaks across tests unless monkeypatched + module reload);
     import-linter won't catch it but it's a hexagonal violation the task
     explicitly asks to avoid
   - Effort: Low

2. **Parameterize `plan_projection`/`plan_unlock` with a `roots` default-valued
   parameter, resolve real base in CLI composition root** (recommended)
   - Add `roots: Mapping[str, Path] = MOUNT_ROOTS` to both function signatures
     (same default value as today → zero test breakage, since no existing test
     passes `roots` explicitly)
   - Add `_resolve_mount_base() -> Path` in `main.py` (mirrors
     `_default_authority`): `FORGE_MOUNT_BASE` env → `XDG_STATE_HOME` env →
     `~/.local/state`, then `/ "odoo-forge"`
   - Add `_build_mount_roots(base: Path) -> dict[str, Path]` building the same 5
     keys under `base`
   - Thread the resolved dict through all 7 core-call sites in `main.py`
     (`validate`, `project`, `unlock`, `run`)
   - Pros: core stays fully pure/env-free (env read lives only at CLI boundary,
     matching the postgres_docker precedent exactly); closes the
     `plan_projection`/`plan_unlock` gap that approach 1 ignores; existing tests
     keep passing unmodified because the default is preserved as a pure-core
     fixture value; new tests can inject arbitrary roots without env mocking
   - Cons: touches 2 core function signatures + ~7 CLI call sites (more surface
     than approach 1); slightly larger diff
   - Effort: Medium

3. **Env read inside `_make_workspace_provider()` only, constant unchanged**
   - Resolve base in CLI, but only pass it into the workspace-provider adapter's
     `scan`/`checkout` calls, leaving `plan_projection`/`plan_unlock` still
     reading the untouched `/mnt` global
   - Pros: smallest touch to `main.py`
   - Cons: does not actually fix the goal — `forge project`/`forge unlock` would
     still target `/mnt` via `plan_projection`/`plan_unlock`, so root would
     still be required for those paths; incomplete fix
   - Effort: Low, but does not meet the stated goal

## Recommendation

**Approach 2.** It is the only option that fully closes the gap (including the
non-obvious `plan_projection`/`plan_unlock` global-read problem discovered
during this exploration) while keeping `odoo_forge` core pure and env-free,
exactly matching the already-established `_default_authority` pattern in
`odoo_forge_postgres_docker`. The default-parameter trick
(`roots: Mapping[str, Path] = MOUNT_ROOTS`) keeps the existing ~10-file test
surface untouched, so the actual required test changes are limited to a handful
of new CLI-level tests asserting `FORGE_MOUNT_BASE`/`XDG_STATE_HOME` resolution
behavior.

## Risks

- Scope creep risk: the task brief undercounted the blast radius (assumed 5
  places); a proposal/spec written against only those 5 will leave
  `forge project`/`forge unlock` still broken on a bare host.
- `plan_projection`/`plan_unlock` currently document themselves as "pure,
  zero I/O" — adding a parameter is a public API/behavior-preserving change, but
  must update those docstrings to reflect injectability.
- `Mount.root` derivation in `src/odoo_forge/backend/plan.py:86`
  (`evidence.container_path.parts[2]`) assumes container-side paths still start
  `/mnt/<root>/...` inside the Docker container — verify whether "mount base"
  configurability is host-side only (recommended) or also changes in-container
  paths; conflating the two would touch `plan_backend` and Docker mount specs
  too. This needs explicit scoping in the proposal phase.

## Ready for Proposal

Yes — investigation is sufficient to proceed to `sdd-propose`. The proposal
should explicitly scope whether the change is host-side-only (mount base under
which repos are checked out) versus also touching in-container `/mnt/*` paths
used by `plan_backend`/Docker mounts, since only the former matches the stated
goal (avoiding root on a bare host).
