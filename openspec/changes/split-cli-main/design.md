# Design: Split `odoo_forge_cli/main.py` by responsibility

## Technical Approach

Formalizes the approved design doc (`docs/superpowers/specs/2026-07-22-cli-main-split-design.md`).
`main.py` (896 lines, verified) mixes three reasons to change: composition/DI,
presentation+I/O+paths, and 16 Typer commands across four families. Split by
cohesion into helper modules plus a `commands/` package. `main.py` keeps only
`app`, the `@app.callback`, and one `register(app)` call per command module.
CLI behavior stays byte-identical: flat hyphenated names, same options, same
output, entry point `forge = "odoo_forge_cli.main:app"` unchanged.

Verified count correction: there are **16** `@app.command` functions (not 17);
`_derive_ref` is a helper, not a command. Families: image (4), manifest (5),
backend (5 + `_derive_ref`), maintenance (2).

## Target Structure & Symbol Assignment (verified line ranges)

| Symbol (current main.py lines) | New home |
|---|---|
| `app`, `_forge_callback` (74, 179-181), `register()` calls | `main.py` (thin, ≤~80 lines) |
| `_make_provider` 79-81, `_make_published_artifact_resolver` 84-86, `_make_workspace_provider` 89-94, `_make_manifest_workspace_provider` 97-108, `_make_backend_provider` 111-117, `_make_image_registry_provider` 120-122, `_doctor_age_key_file` 125-133 | `_composition.py` |
| `_format_drift` 238-254, `_format_missing_dependencies` 257-260, `_render_validation_errors` 289-292 | `_presentation.py` |
| `_resolve_mount_base` 136-163, `_host_roots` 166-176, `_read_manifest_data` 184-194, `_load_lock` 197-212, `_write_lock_atomic` 215-235, `_check_module_dependencies` 263-286 | `_support.py` |
| `image_resolve` 295, `image_publish` 307, `image_pull` 321, `image_exists` 335 | `commands/image.py` |
| `validate` 349, `onboard` 415, `lock` 493, `project` 543, `unlock` 589 | `commands/manifest.py` |
| `run` 626, `status` 707, `_derive_ref` 746-749, `stop` 752, `logs` 778, `exec_` 805 | `commands/backend.py` |
| `doctor` 845, `rotate_enterprise_credential` 868 | `commands/maintenance.py` |
| `__all__` re-exports 890-896 (ec symbols) | Dropped (no facade) |

Constraint: no module > ~250 lines. `GitWorkspaceProvider` and the ec imports
(`_bind_*`, `_make_enterprise_credential_resolver`, `_preflight_*`) move to the
modules that use them (`_composition`, `commands/manifest`, `commands/maintenance`).

## Architecture Decisions

### Decision: `register(app)` registration seam
**Choice**: Each `commands/*.py` exposes `def register(app: typer.Typer) -> None`
that binds its functions via `app.command(name=...)(fn)`. `main.py` builds the
single `app` and calls each `register(app)`.
**Alternatives**: (a) command modules import `app` from `main` and decorate
directly; (b) a shared `app.py` module holding `app`.
**Rationale**: (a) creates a cycle (`main` imports command modules to register
them, command modules import `main` for `app`). `register(app)` inverts the
dependency — command modules never import `main`, so no cycle. Chosen over (b)
because `app` must live where the entry point resolves it (`main:app`).

### Decision: module-qualified helper access (makes patch targets deterministic)
**Choice**: Command modules import helper *modules* and call qualified
(`_composition.make_backend_provider`, `_support.resolve_mount_base`), NOT
`from _support import resolve_mount_base`.
**Alternatives**: `from x import symbol` binding into each caller.
**Rationale**: Python resolves a bare imported name against the *caller's*
module globals at call time. With `from`-imports, a helper used by N command
modules would need N patch targets, and a helper called both directly by a
command and internally by another helper (e.g. `_resolve_mount_base`, used by
`validate` directly AND inside `_host_roots`) would fragment into divergent
targets — a silent test-correctness hazard. Module-qualified access gives
exactly ONE canonical patch target per symbol: its definition module.

### Decision: flat command names preserved (no Typer sub-apps)
**Choice**: Keep `forge image-resolve`, not `forge image resolve`.
**Alternatives**: Typer command groups / `add_typer` sub-apps per family.
**Rationale**: Groups change the public CLI surface and break existing user
scripts for zero requested benefit. `register(app)` intentionally keeps names
flat and behavior byte-identical.

### Decision: no re-export facade
**Choice**: Do NOT re-export moved symbols from `main`. Repoint every test
patch/import to the symbol's new home.
**Alternatives**: keep `from _composition import *` in `main` so old
`patch("odoo_forge_cli.main.X")` still resolves.
**Rationale**: `monkeypatch.setattr("odoo_forge_cli.main.X", ...)` would rebind
`main`'s attribute, but the real caller (now in `_composition`/`commands.*`)
resolves `X` through *its own* module — the patch silently no-ops and the test
passes against unpatched production code. A facade makes this failure invisible.
No facade forces the correct target.

## Data Flow

    main.py: app = Typer(); @app.callback
        └─ register(app) ×4  ─→ commands/{image,manifest,backend,maintenance}.py
                                     │ call qualified
                                     ▼
                          _composition (DI) / _support (I/O+paths) / _presentation
                                     │
                                     ▼
                                odoo_forge core + adapters

## Test Strategy — concrete repoint inventory

Patch target = symbol's definition module (module-qualified rule). 27 CLI files;
`app` stays in `main`, so `CliRunner`-on-`app` invocations are untouched.

| Test file | Current target(s) | Repoint to |
|---|---|---|
| `test_image_registry.py` | `main._make_image_registry_provider`; `main._make_backend_provider` (l.261) | `_composition.*` |
| `test_backend.py` | `main._make_workspace_provider`, `main._make_backend_provider`, `main._resolve_mount_base`; `main.plan_backend` (l.320); `import plan_backend from main` (l.29); `main._make_backend_provider()` direct (l.337) | `_composition.*`, `_support._resolve_mount_base`, `commands.backend.plan_backend` |
| `test_validate.py` | `main._resolve_mount_base`, `main._make_workspace_provider` | `_support`, `_composition` |
| `test_onboard.py` | `main._make_workspace_provider`, `main._resolve_mount_base` (patch + direct call l.45) | `_composition`, `_support` |
| `test_project.py` | `main._make_workspace_provider`, `main._resolve_mount_base`; `setitem(main.__dict__,"GitWorkspaceProvider")` (l.276) | `_composition.*` |
| `test_unlock.py` | `main._make_workspace_provider`, `main._resolve_mount_base` | `_composition`, `_support` |
| `test_lock.py` | `main._make_provider`, `main._make_published_artifact_resolver`, `main._make_enterprise_credential_resolver`; `main._load_lock` direct (l.297,311) | `_composition.*`, `_support._load_lock`, `commands.manifest` (or `enterprise_credential`) |
| `test_doctor.py` | `main._doctor_age_key_file`, `main._make_enterprise_credential_resolver` | `_composition._doctor_age_key_file`, `commands.maintenance` |
| `test_enterprise_credential.py` | `main._make_provider`/`_make_workspace_provider`/`_make_enterprise_credential_resolver`; `main._bind_*` direct | `_composition.*`; `ec._bind_*` (already imports `ec`) |
| `test_mount_base.py` | `from main import _resolve_mount_base` | `from _support import resolve_mount_base` |

Unchanged: `test_rotate_enterprise_credential.py` (patches
`odoo_forge_docker...subprocess.run`; only `app` import), all pure
`CliRunner(app,...)` assertions, `os.replace`/`subprocess` global patches,
`conftest.py` (env-var only; `main` reference is docstring). `_make_workspace_provider`
patched at `_composition` still governs `_make_manifest_workspace_provider`
(same module, intra-module bare-name resolution).

| Layer | What | Approach |
|---|---|---|
| Unit | helper modules importable, no cycle | import smoke test per module + `commands` package |
| Integration | every command still registered on `app` | existing `CliRunner` suite, unmodified |
| Contract | entry point + import-linter | `forge --help` lists all 16; `lint-imports` green |

## Threat Matrix

N/A — pure internal move. No routing, shell command, subprocess, VCS/PR
automation, executable-file classification, or process-integration boundary is
introduced or changed; subprocess/docker/git behavior is relocated verbatim.

## Migration / Rollout

5 chained PRs, lowest-risk-first, each ≤400 changed lines, full suite green
before merge:

1. **PR1** — extract `_composition.py`, `_presentation.py`, `_support.py`;
   repoint helper-import/patch tests (`test_mount_base`, `_load_lock`/`_resolve_mount_base` direct). No commands move.
2. **PR2** — `commands/image.py` (most isolated); repoint `test_image_registry`.
3. **PR3** — `commands/maintenance.py`; repoint `test_doctor`.
4. **PR4** — `commands/backend.py` + `_derive_ref` (heaviest monkeypatch surface); repoint `test_backend`.
5. **PR5** — `commands/manifest.py`; `main.py` becomes thin; drop `__all__` re-exports; repoint `test_validate/onboard/project/unlock/lock/enterprise_credential`.

Rollback: each PR is independent and behavior-preserving; revert its merge commit.

## Success Criteria

- `forge` CLI byte-identical (existing `CliRunner` suite green, unmodified).
- `main.py` ≤ ~80 lines; no module > ~250 lines.
- Full suite green after each PR; import smoke check (no cycle) per PR.
- `lint-imports` contract (`forbidden_modules=["odoo_forge_cli"]`) still passes.

## Open Questions

- [ ] Confirm PR5's manifest repoint stays ≤400 lines; if not, split validate/onboard from lock/unlock/project into two slices.
