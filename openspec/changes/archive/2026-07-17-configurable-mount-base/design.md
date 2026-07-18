# Design: Configurable Host Mount Base (decouple host/container roots)

## Technical Approach

Split the single `MOUNT_ROOTS` table into two tables built by one helper. The
CONTAINER base stays fixed at `/mnt` (structural: `plan_backend` derives the
root via `container_path.parts[2]`, `backend/plan.py:86`). The HOST base is
resolved only at the CLI composition root from env, mirroring
`_default_authority` (`odoo_forge_postgres_docker/provider.py:481-489`). Core
stays pure/env-free; injectability flows through default-valued `roots`
parameters so the existing ~10-file test surface stays green by construction.

## Architecture Decisions

| Decision | Choice | Rationale / Rejected |
|---|---|---|
| Container base | `CONTAINER_MOUNT_BASE = Path("/mnt")` named constant in core; `MOUNT_ROOTS = build_mount_roots(CONTAINER_MOUNT_BASE)` | Pure data, not I/O, so allowed in core. Documents WHY `/mnt` is fixed (`parts[2]` shape). Rejected: inline literals scattered across tables. |
| One builder | Single `build_mount_roots(base) -> dict[str, Path]` builds both host and container tables | DRY; the 5 root names must stay identical between tables or `_match_root_and_layer`/`plan_backend` desync. Rejected: two hand-written dicts. |
| Env boundary | `_resolve_mount_base()` reads env ONLY in `main.py` | Preserves hexagonal purity + test determinism. `os` is not import-linter-forbidden, but env-in-core violates the "pure, zero I/O" contract. Rejected: env read at core import time (exploration Approach 1). |
| Injection shape | Default-valued `roots` params; host table = injected, container table = fixed | Zero breakage: no existing test passes `roots`, so defaults reproduce today. Rejected: mandatory params (breaks 10 files). |

## Data Flow

```
env (FORGE_MOUNT_BASE | XDG_STATE_HOME | ~/.local/state)
      │  _resolve_mount_base()            [main.py only]
      ▼
build_mount_roots(base) ── HOST table ──┐
build_mount_roots(/mnt)  ── CONTAINER ──┤ (== MOUNT_ROOTS default)
      ▼                                 ▼
scan / source_path / target_path    container_path (fixed /mnt)
(plan_projection, plan_unlock,      (build_mount_planning_view
 materialize_state, scan match)      MountEvidence.container_path)
```

HOST table feeds: `plan_projection` targets, `plan_unlock` source/dest, scan
paths, `materialize_state`, and `_match_root_and_layer` (scanned host paths).
CONTAINER (fixed) table feeds ONLY `MountEvidence.container_path`.

## Interfaces / Contracts

```python
# projection.py (core)
CONTAINER_MOUNT_BASE: Path = Path("/mnt")  # fixed: container FS convention; plan_backend parts[2]
def build_mount_roots(base: Path) -> dict[str, Path]: ...   # 5 keys under base
MOUNT_ROOTS: dict[str, Path] = build_mount_roots(CONTAINER_MOUNT_BASE)

def plan_projection(manifest, lock, roots: Mapping[str, Path] = MOUNT_ROOTS) -> WorkspacePlan  # :106 :136 roots[mount_root]
def plan_unlock(manifest, layer_name, repo_url, roots: Mapping[str, Path] = MOUNT_ROOTS) -> UnlockPlan  # :143 :185-186
def build_mount_planning_view(manifest, lock, scanned, state,
    roots: Mapping[str, Path],                                 # HOST: scan match + dedup + expected_path
    container_roots: Mapping[str, Path] = MOUNT_ROOTS) -> MountPlanningView
```

Edits: `build_mount_planning_view` — `_match_root_and_layer` (:278) and
`expected_path` (:292-296) keep using `roots` (host); `MountEvidence`
(:322-330) keeps `source_path=evidence.path` but `container_path` (:327) and
the dedup `container_paths` (:270-272) switch to `container_roots[step.mount_root]`.
Update `plan_projection`/`plan_unlock` docstrings: "pure, zero I/O; roots
injectable, defaults to the fixed container table."

```python
# main.py (composition root, near lines 60-79)
def _resolve_mount_base() -> Path:
    base = os.environ.get("FORGE_MOUNT_BASE")
    if base:
        return Path(base).expanduser()
    state = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(state).expanduser() / "odoo-forge"
_HOST_ROOTS = build_mount_roots(_resolve_mount_base())
```

Call-site edits: `validate` (252-253) and `run` (443-450) — `provider.scan(list(_HOST_ROOTS.values()))`,
`materialize_state(scanned, _HOST_ROOTS)`, `build_mount_planning_view(..., _HOST_ROOTS)`
(container defaults to `/mnt`). `project` (349) — `plan_projection(parsed, loaded_lock, _HOST_ROOTS)`.
`unlock` (386) — `plan_unlock(parsed, layer, repo, _HOST_ROOTS)`.

## Testing Strategy (STRICT TDD — RED first)

| Layer | What to Test | Approach / Seam |
|---|---|---|
| Unit | `_resolve_mount_base`: unset→`~/.local/state/odoo-forge`; `FORGE_MOUNT_BASE` override; `XDG_STATE_HOME` influence; `~`/relative/trailing-slash | `monkeypatch.setenv`; pure return, no FS/docker |
| Unit | `build_mount_roots(base)` maps 5 keys under base | Pure dict assertion |
| Unit | `container_path` stays `/mnt/<root>/...` when host base differs | Inject host roots ≠ `/mnt`, assert `MountEvidence.container_path` fixed |
| Unit | `plan_projection`/`plan_unlock` honor injected `roots` | Pass non-`/mnt` roots, assert targets |
| Regression | 10 existing files stay green | Defaults preserve `/mnt`; `test_projection*` still import `MOUNT_ROOTS` |

Seams making it test-drivable without FS/docker: `_resolve_mount_base` (env→Path,
pure), `build_mount_roots` (pure), and the two-table `roots`/`container_roots`
injection points.

## Edge Cases

- Unset envs → `~/.local/state/odoo-forge`. `~` and `$VAR` via `.expanduser()`
  (no `os.path.expandvars`; keep literal `$`). Relative `FORGE_MOUNT_BASE` kept
  relative (caller's cwd) — documented, not normalized. Trailing slash is inert
  under `Path` join. Empty-string env treated as unset (`if base:`).

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or process-integration boundary changes. Env is read as data
only; no value is executed.

## Migration / Rollout

No data migration. `FORGE_MOUNT_BASE=/mnt` reproduces today's behavior exactly;
`/mnt` stops being the host default. Rollback reverts `projection.py` +
`main.py` together in one release. No provider or schema change.

## Open Questions

None.
