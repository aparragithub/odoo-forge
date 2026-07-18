# Proposal: Configurable Host Mount Base (decouple host/container roots)

## Intent

Workspace mount roots are hardcoded to `/mnt/*` via the module-level `MOUNT_ROOTS`
constant (`src/odoo_forge/manifest/projection.py:33`). Writing under `/mnt`
requires root on a bare host, which blocks `forge project`, `forge unlock`, and
`forge run` end-to-end for a normal user. Make the HOST base configurable while
keeping the CONTAINER base fixed, so the tool runs rootless by default.

## Scope

### In Scope
- Host base resolution at the CLI composition root only (`main.py`, mirroring
  `_default_authority()` in `odoo_forge_postgres_docker/provider.py:481-489`):
  `FORGE_MOUNT_BASE` env → `${XDG_STATE_HOME:-~/.local/state}` → `/ "odoo-forge"`.
  New default `~/.local/state/odoo-forge`; `/mnt` stops being the host default.
- Decouple host and container root tables (currently coupled: one `roots` table
  feeds BOTH `MountEvidence.source_path` and `.container_path`, projection.py:326-327).
  Introduce a single named `CONTAINER_MOUNT_BASE = Path("/mnt")` constant and a
  `_build_mount_roots(base)` helper that builds both tables identically. Container
  base stays `/mnt` by design and is documented as fixed.
- `build_mount_planning_view` and planning core take TWO root tables: host for
  `source_path`/scanning, fixed container for `container_path`.
- Close the transitive-global gap: parameterize `plan_projection` (projection.py:106)
  and `plan_unlock` (projection.py:143) with a `roots` argument, default preserved.

### Out of Scope
- In-container paths — they stay `/mnt` by design (`plan_backend` derives the
  mount root via `container_path.parts[2]`, backend/plan.py:86, assuming `/mnt/<root>/...`).
- Manifest schema, lockfile format, and CLI command surface — no new flags
  (env-var driven only).
- Core reading env directly — purity/import-linter boundary must be preserved.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `manifest`: projection mount-root table becomes injectable and host/container
  bases are decoupled; the fixed `/mnt/<root>/...` container shape is preserved.

## Approach

Approach 2 from exploration. Keep `odoo_forge` core pure and env-free by reading
env only at the CLI boundary; thread resolved host roots + fixed container roots
through all seven core call sites (`validate`, `project`, `unlock`, `run`).
Default-valued `roots` parameters keep the existing ~10-file test surface intact.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/manifest/projection.py` | Modified | Named container base, `_build_mount_roots`, host/container split, `plan_projection`/`plan_unlock` params |
| `src/odoo_forge_cli/main.py` | Modified | `_resolve_mount_base()`/`_build_mount_roots()`; thread roots through 4 commands |
| `src/odoo_forge_postgres_docker/provider.py` | Reference | XDG pattern to mirror (not modified) |
| `tests/` (10 files) | Modified | New CLI resolution tests; existing `/mnt` assertions preserved via default |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Naive single-table change moves container path, breaking `plan_backend.parts[2]` | High | Explicit host/container decoupling; `/mnt` fixed and documented |
| Undercounted blast radius leaves `project`/`unlock` broken on bare host | Med | Parameterize `plan_projection`/`plan_unlock` (transitive global) |
| Core reads env → hexagonal/test-determinism regression | Med | Env read confined to CLI composition root |
| Test breakage across 10 files | Low | Preserve `MOUNT_ROOTS` default; add only CLI-level tests |

## Rollback Plan

Revert projection and `main.py` wiring together in one release. No data migration:
`/mnt` remains reachable via `FORGE_MOUNT_BASE=/mnt`. No provider or schema change.

## Dependencies

None.

## Success Criteria

- [ ] `forge project`/`unlock`/`run` succeed rootless under `~/.local/state/odoo-forge`.
- [ ] `FORGE_MOUNT_BASE` and `XDG_STATE_HOME` resolution honored in order; `/mnt` reachable via override.
- [ ] Container-side paths remain `/mnt/<root>/...`; `plan_backend` unchanged.
- [ ] Core stays env-free; import-linter, mypy, and existing tests pass.

## Proposal question round

Direction is pre-agreed with the requester (host-configurable / container-fixed
decoupling). Assumptions to confirm before spec: (1) host default is
`~/.local/state/odoo-forge` with `/mnt` no longer default; (2) resolution order
`FORGE_MOUNT_BASE` → `XDG_STATE_HOME` → `~/.local/state`; (3) no new CLI flag.
Flag here if any assumption should change.
