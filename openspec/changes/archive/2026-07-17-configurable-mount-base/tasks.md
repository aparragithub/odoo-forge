# Tasks: Configurable Host Mount Base (decouple host/container roots)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~150-250 (2 source files + tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | N/A |

Decision needed before apply: No
Chained PRs recommended: No
400-line budget risk: Low

### Suggested Work Units

| Unit | Estimated changed lines | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|---|
| 1 | ~150-250 | Single PR; TDD `build_mount_roots`/host-container split in core, then `_resolve_mount_base` + wiring in the CLI composition root. | PR 1 | `uv run pytest -q` | N/A (pure core; CLI tests mock the boundary) | `src/odoo_forge/manifest/projection.py`, `src/odoo_forge_cli/main.py` |

Full suite command (repo default, per `pyproject.toml` `[tool.pytest.ini_options]` addopts `-m 'not integration'`):

```
uv run pytest -q
```

## Phase 1: Core — `projection.py` host/container root split

Satisfies: manifest spec "Host and container mount root tables are decoupled";
proposal "Introduce a single named `CONTAINER_MOUNT_BASE` ... and a
`_build_mount_roots(base)` helper".

- [x] 1.1 RED: In `tests/manifest/test_projection.py`, add a test asserting
      `build_mount_roots(base)` returns the 5 keys (`community`, `custom`,
      `localization`, `enterprise`, `worktrees`) each equal to `base / key`,
      for an arbitrary non-`/mnt` base.
- [x] 1.2 GREEN: In `src/odoo_forge/manifest/projection.py`, add
      `CONTAINER_MOUNT_BASE = Path("/mnt")` (with the "fixed: container FS
      convention; `plan_backend` parts[2]" comment from the design) and
      `build_mount_roots(base: Path) -> dict[str, Path]`; redefine
      `MOUNT_ROOTS = build_mount_roots(CONTAINER_MOUNT_BASE)` in terms of the
      new helper (no behavior change — same keys/values as today).
- [x] 1.3 RED: Add tests asserting `plan_projection(...)` and
      `plan_unlock(...)` honor an injected `roots` mapping (non-`/mnt` base)
      for their target/source/dest paths, in addition to existing
      default-`MOUNT_ROOTS` assertions.
- [x] 1.4 GREEN: Parameterize `plan_projection(manifest, lock, roots:
      Mapping[str, Path] = MOUNT_ROOTS)` and `plan_unlock(manifest,
      layer_name, repo_url, roots: Mapping[str, Path] = MOUNT_ROOTS)`; update
      their docstrings to state "pure, zero I/O; roots injectable, defaults
      to the fixed container table."
- [x] 1.5 RED: Add a guard test asserting `build_mount_planning_view(...)`
      keeps `MountEvidence.container_path` fixed at `/mnt/<root>/...` when
      the injected host `roots` table uses a non-`/mnt` base, while
      `source_path`/scan-matching use the host base.
- [x] 1.6 GREEN: Give `build_mount_planning_view` a separate `container_roots:
      Mapping[str, Path] = MOUNT_ROOTS` parameter; keep `_match_root_and_layer`
      and `expected_path` on the host `roots` table; switch
      `MountEvidence.container_path` and the dedup `container_paths` set to
      `container_roots[step.mount_root]`.
- [x] 1.7 Verify Phase 1 with `uv run pytest tests/manifest/test_projection.py tests/manifest/test_projection_roundtrip.py -q`; confirm no `os.environ` read was introduced in `projection.py`.

## Phase 2: CLI — host base resolution and wiring

Satisfies: manifest spec "Host mount base resolves at the CLI composition
root"; "forge validate/project/unlock" modified requirements.

- [x] 2.1 RED: Add CLI-level tests (new `tests/cli/test_mount_base.py` or
      extend `tests/cli/test_validate.py`) covering: no env set →
      `~/.local/state/odoo-forge`; `FORGE_MOUNT_BASE=/custom/path` overrides
      regardless of `XDG_STATE_HOME`; `XDG_STATE_HOME=/xdg/state` (no
      `FORGE_MOUNT_BASE`) → `/xdg/state/odoo-forge`; `FORGE_MOUNT_BASE=/mnt`
      reproduces the pre-change hardcoded `/mnt/*` host paths exactly.
- [x] 2.2 GREEN: In `src/odoo_forge_cli/main.py`, add `_resolve_mount_base()`
      mirroring `_default_authority()` (`odoo_forge_postgres_docker/provider.py:481-489`):
      `FORGE_MOUNT_BASE` env (if truthy) → else `${XDG_STATE_HOME:-~/.local/state}`,
      both `.expanduser()`d, then `/ "odoo-forge"`; treat empty-string env as
      unset.
- [x] 2.3 GREEN: Build `_HOST_ROOTS = build_mount_roots(_resolve_mount_base())`
      at the CLI composition root; import `build_mount_roots` from
      `odoo_forge.manifest.projection`.
- [x] 2.4 RED: Add/extend `tests/cli/test_validate.py` and
      `tests/cli/test_backend.py` (`run`) asserting `provider.scan(...)`,
      `materialize_state(...)`, and `build_mount_planning_view(...)` are
      called with `_HOST_ROOTS` (host paths), not the fixed `/mnt` table.
- [x] 2.5 GREEN: Thread `_HOST_ROOTS` through `validate` (`provider.scan(list(_HOST_ROOTS.values()))`,
      `materialize_state(scanned, _HOST_ROOTS)`, `build_mount_planning_view(...,
      _HOST_ROOTS)`) and `run`, leaving `container_roots` on its `MOUNT_ROOTS`
      default (fixed `/mnt`).
- [x] 2.6 RED: Extend `tests/cli/test_project.py` (`project`) and
      `tests/cli/test_unlock.py` (`unlock`) asserting `plan_projection(...)`/
      `plan_unlock(...)` are called with `_HOST_ROOTS`. (Deviation: the task
      description named `tests/cli/test_lock.py` for the `project` command,
      but that file covers `forge lock`; the actual `project` command tests
      live in `tests/cli/test_project.py`, which is what was extended.)
- [x] 2.7 GREEN: Update `project` call site to
      `plan_projection(parsed, loaded_lock, _HOST_ROOTS)` and `unlock` call
      site to `plan_unlock(parsed, layer, repo, _HOST_ROOTS)`.
- [x] 2.8 Verify Phase 2 with `uv run pytest tests/cli/test_validate.py tests/cli/test_backend.py tests/cli/test_project.py tests/cli/test_unlock.py tests/cli/test_mount_base.py -q`.

## Phase 3: Full-suite and boundary verification

- [x] 3.1 Run the full suite: `uv run pytest -q` — confirm all previously-passing
      files (existing `/mnt` assertions, pinned via a new `tests/conftest.py`
      that sets `FORGE_MOUNT_BASE=/mnt` at collection time since `_HOST_ROOTS`
      is resolved once at `main.py` import time) stay green, plus the new
      tests from Phases 1-2. Result: 697 passed, 14 deselected.
- [x] 3.2 Run import-linter to confirm `odoo_forge` core still has zero env
      reads and the hexagonal boundary holds: `uv run lint-imports` — 6
      contracts kept, 0 broken.
- [x] 3.3 Manual/inspection check: grep `projection.py` for `os.environ`/`os.getenv`
      to confirm zero occurrences (core purity requirement). Confirmed: 0
      matches.
- [x] 3.4 Record final evidence: full suite pass, import-linter pass, and the
      backward-compat scenario (`FORGE_MOUNT_BASE=/mnt` reproduces pre-change
      `/mnt/*` host paths) confirmed via
      `TestResolveMountBase::test_forge_mount_base_mnt_reproduces_the_pre_change_host_paths`.
