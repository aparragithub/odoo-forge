# Apply Progress: `split-cli-main`

## PR1 — `_composition.py` + `_presentation.py` + `_support.py` — COMPLETE

Status: all 11 tasks (1.1-1.11) done. Full suite green, `lint-imports` green,
`forge --help` resolves, no circular imports. No `@app.command` function was
moved — all 16 commands remain in `main.py`.

### What changed

- Created `src/odoo_forge_cli/_composition.py`: `_make_provider`,
  `_make_published_artifact_resolver`, `_make_workspace_provider`,
  `_make_manifest_workspace_provider`, `_make_backend_provider`,
  `_make_image_registry_provider`, `_doctor_age_key_file`, plus the
  `_WORKSPACE_PROVIDER_TIMEOUT_SECONDS` module-level global and the
  `GitWorkspaceProvider` import.
- Created `src/odoo_forge_cli/_presentation.py`: `_format_drift`,
  `_format_missing_dependencies`, `_render_validation_errors`.
- Created `src/odoo_forge_cli/_support.py`: `_resolve_mount_base`,
  `_host_roots`, `_read_manifest_data`, `_load_lock`, `_write_lock_atomic`,
  `_check_module_dependencies`. `_check_module_dependencies` calls
  `_presentation._format_missing_dependencies` module-qualified (the one
  genuinely necessary cross-new-module call the split introduces).
- `main.py`: removed the 16 moved function bodies; dropped now-dead imports
  (`os`, `json`, `tempfile`, `yaml`, `Lockfile`, `ManifestInputError`,
  `ModuleDependencyError`, `build_mount_roots`, `ordered_addons_roots`,
  `build_module_index`, `find_missing_dependencies`, `GitWorkspaceProvider`,
  `DriftEntry`); added `from odoo_forge_cli import _composition, _presentation,
  _support`; updated every command body's call site to module-qualified
  access (`_composition._make_backend_provider(...)`,
  `_support._resolve_mount_base()`, `_presentation._render_validation_errors(...)`,
  etc.) instead of bare-name calls. 336 lines removed from `main.py`
  net-net (896 -> ~560 lines pre-existing content minus moved bodies,
  plus qualification edits).
- The pre-existing `__all__` re-export block (ec symbols, lines ~890-896)
  is untouched — dropping it is explicitly PR5b scope per design's migration
  table, unrelated to this PR's three new modules.

### Test repoints (module-qualified patch targets)

Scope was wider than the two files tasks.md names literally
(`test_mount_base.py`, `test_lock.py`), because task 1.5 requires
module-qualified access in ALL of `main.py`'s command bodies (not just
`lock`) so that every moved symbol has exactly one canonical patch target
regardless of which future PR moves its caller command. Repointed:

| Test file | Symbol(s) repointed | New target |
|---|---|---|
| `tests/cli/test_mount_base.py` | `_resolve_mount_base` (direct import) | `from odoo_forge_cli import _support`; calls become `_support._resolve_mount_base()` |
| `tests/cli/test_lock.py` | `_load_lock` (direct calls, l.297/311), `_make_provider`, `_make_published_artifact_resolver`, `_make_workspace_provider` (monkeypatch) | `_support`, `_composition` |
| `tests/cli/test_doctor.py` | `_doctor_age_key_file` (monkeypatch) | `_composition` |
| `tests/cli/test_backend.py` | `_make_workspace_provider`, `_make_backend_provider` (monkeypatch + one direct call at former l.337), `_resolve_mount_base` (monkeypatch) | `_composition`, `_support` |
| `tests/cli/test_validate.py` | `_resolve_mount_base`, `_make_workspace_provider` (monkeypatch) | `_support`, `_composition` |
| `tests/cli/test_onboard.py` | `_resolve_mount_base` (module-level direct call + monkeypatch), `_make_workspace_provider` (monkeypatch) | `_support`, `_composition` |
| `tests/cli/test_unlock.py` | `_make_workspace_provider`, `_resolve_mount_base` (monkeypatch) | `_composition`, `_support` |
| `tests/cli/test_project.py` | `_make_workspace_provider`, `_resolve_mount_base` (monkeypatch); `setitem(main.__dict__, "GitWorkspaceProvider", ...)` | `_composition`, `_support`; `setitem(_composition.__dict__, ...)` |
| `tests/cli/test_image_registry.py` | `_make_image_registry_provider`, `_make_backend_provider` (monkeypatch) | `_composition` |
| `tests/cli/test_enterprise_credential.py` | `_make_provider`, `_make_workspace_provider` (monkeypatch) | `_composition` (its `_make_enterprise_credential_resolver`/`_bind_*` patches on `main`/`ec` are untouched — out of PR1 scope, belongs to `enterprise_credential.py`) |

`tests/cli/test_rotate_enterprise_credential.py` and `conftest.py`:
confirmed unchanged, as the design predicted.

### Naming deviation (documented, deliberate)

`tasks.md` (1.6) and `design.md`'s test-repoint table literally write
`from _support import resolve_mount_base` (no leading underscore) for
`test_mount_base.py`, while every other row in the same table — including
PR4's `test_backend.py` row for the identical symbol — writes
`_support._resolve_mount_base` (with the underscore). Since Python cannot
give one symbol two different canonical names without either (a) breaking
the "one canonical patch target" invariant that is this whole PR's stated
purpose, or (b) leaving `test_mount_base.py` non-hermetic and inconsistent
with `test_backend.py`'s expectation for PR4, I treated the underscore-less
spelling as a documentation slip and kept `_resolve_mount_base` (with
underscore) as the one real name, imported and called module-qualified
(`_support._resolve_mount_base()`) everywhere, including in
`test_mount_base.py`. Flagging this explicitly for `sdd-verify`.

### Verification (real output)

```
$ uv run pytest -q
... (coverage table omitted)
901 passed, 17 deselected in 6.94s
```
The 17 deselected are pre-existing marker-excluded tests (default pytest
config); confirmed unrelated to this change — running with `-m ""` reveals
2 of them require a live Docker daemon (`test_docker_provider_integration.py`),
which is an environment limitation, not a regression from this PR.

```
$ uv run lint-imports
Analyzed 104 files, 329 dependencies.
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Core never imports the docker adapter KEPT
Core never imports the registry adapter KEPT
Contracts: 6 kept, 0 broken.
```

```
$ uv run forge --help
exit=0, 47 lines, all 16 commands listed unchanged (image-resolve,
image-publish, image-pull, image-exists, validate, onboard, lock, project,
unlock, run, status, stop, logs, exec, doctor, rotate-enterprise-credential)
```

```
$ uv run python -c "import odoo_forge_cli._composition; import odoo_forge_cli._presentation; import odoo_forge_cli._support; import odoo_forge_cli.main"
no cycle, all import cleanly
```

Command-function count check: `rg -c "@app.command" src/odoo_forge_cli/main.py`
→ 16 (unchanged from pre-PR1 baseline; zero commands moved).

`uv run ruff check` and `uv run ruff format --check` both clean on
`src/odoo_forge_cli/` and `tests/cli/`.

### Diffstat

```
 openspec/changes/split-cli-main/tasks.md |  22 +-
 src/odoo_forge_cli/main.py               | 336 +++++--------------------------
 tests/cli/test_backend.py                | 106 +++++-----
 tests/cli/test_doctor.py                 |   8 +-
 tests/cli/test_enterprise_credential.py  |  26 +--
 tests/cli/test_image_registry.py         |  24 +--
 tests/cli/test_lock.py                   |  22 +-
 tests/cli/test_mount_base.py             |  16 +-
 tests/cli/test_onboard.py                |  28 +--
 tests/cli/test_project.py                |  20 +-
 tests/cli/test_unlock.py                 |  14 +-
 tests/cli/test_validate.py               |  20 +-
 12 files changed, 210 insertions(+), 432 deletions(-)

New files (not yet tracked by git, awaiting orchestrator commit):
 src/odoo_forge_cli/_composition.py   (75 lines)
 src/odoo_forge_cli/_presentation.py  (39 lines)
 src/odoo_forge_cli/_support.py       (123 lines)
```

## Not started

PR2 (`commands/image.py`), PR3 (`commands/maintenance.py`), PR4
(`commands/backend.py`), PR5a/PR5b (`commands/manifest.py`) — all deferred
per PR1-only scope instruction. No `@app.command` body has been touched;
they remain verbatim in `main.py`, now calling the three new modules
module-qualified instead of via bare names.
