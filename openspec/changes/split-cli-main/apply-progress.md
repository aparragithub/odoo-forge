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

## PR2 — `commands/image.py` — COMPLETE

Status: all 7 tasks (2.1-2.7) done. Full suite green (unchanged count vs
PR1 baseline), `lint-imports` green, `forge --help` shows all 16 commands,
CLI surface byte-identical, no circular imports.

### What changed

- Created `src/odoo_forge_cli/commands/__init__.py` (new package, docstring
  only).
- Created `src/odoo_forge_cli/commands/image.py`: moved `image_resolve`,
  `image_publish`, `image_pull`, `image_exists` verbatim (bodies unchanged,
  same module-qualified `_composition._make_image_registry_provider()`
  calls carried over from PR1); added `register(app: typer.Typer) -> None`
  that binds all four via `app.command(name=...)` with the exact
  pre-existing flat hyphenated names (`image-resolve`, `image-publish`,
  `image-pull`, `image-exists`). Imports only `typer`,
  `odoo_forge.image_registry` (errors + reference normalizers), and
  `odoo_forge_cli._composition` — no import of `odoo_forge_cli.main`,
  confirmed via `rg`.
- `main.py`: removed the four `@app.command` bodies (63 lines); added
  `from odoo_forge_cli.commands import image` and a single `image.register(app)`
  call placed immediately after the `_forge_callback`. Trimmed now-unused
  imports `normalize_digest_image_reference` /
  `normalize_publishable_image_reference` (both only used by the moved
  commands); kept `RegistryError` and `normalize_image_reference` since
  `run`/`status` (still in `main.py`) use them.
- `main.py` now has 12 `@app.command` decorators (down from 16); the four
  image commands live in `commands/image.py`.

### Test repoint (task 2.4) — already satisfied by PR1

`tests/cli/test_image_registry.py` already patches
`_composition._make_image_registry_provider` and
`_composition._make_backend_provider` (not `main.*`) — task 1.8 in PR1
widened the module-qualification repoint to every test file touching a
PR1-moved symbol, including this one, ahead of schedule. Since
`commands/image.py` calls these factories module-qualified from
`_composition` (identical call-site shape to the pre-PR2 `main.py` body),
the existing patch targets remain the single canonical binding — no edit
was needed. Verified by inspection (`rg` showing all patches already target
`_composition`) and by the full green run below (a stale/no-op patch would
have surfaced as a passing-but-unexercised test; the fake-provider
assertions on `resolve_calls`/`publish_calls`/etc. would fail if the real
provider had been invoked instead).

### Verification (real output)

```
$ uv run pytest tests/cli/test_image_registry.py -v   # RED baseline, pre-move
19 passed
```

```
$ uv run pytest -q   # GREEN, full suite post-move
901 passed, 17 deselected in 6.74s
```
(Identical to PR1's post-verification count — zero regressions, zero new
skips.)

```
$ uv run lint-imports
Analyzed 106 files, 334 dependencies.
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Core never imports the docker adapter KEPT
Core never imports the registry adapter KEPT
Contracts: 6 kept, 0 broken.
```

```
$ uv run python -c "import odoo_forge_cli.commands.image; import odoo_forge_cli.main"
no cycle, ok
```

```
$ rg -c "@app.command" src/odoo_forge_cli/main.py
12
```

```
$ uv run forge --help
exit=0, all 16 commands listed unchanged, same order, same help text
$ uv run forge image-resolve --help
$ uv run forge image-publish --help
$ uv run forge image-pull --help
$ uv run forge image-exists --help
all four byte-identical to pre-PR2 output (same options, same required
--ref flag, same help strings)
```

`uv run ruff check` and `uv run ruff format --check` both clean on
`src/odoo_forge_cli/`.

### Diffstat

```
 openspec/changes/split-cli-main/tasks.md |   14 +-
 src/odoo_forge_cli/main.py               |   72 +------
 2 files changed (tracked)

New files (not yet tracked by git, awaiting orchestrator commit):
 src/odoo_forge_cli/commands/__init__.py  (2 lines)
 src/odoo_forge_cli/commands/image.py     (62 lines)
```

## PR3 — `commands/maintenance.py` — COMPLETE

Status: all 7 tasks (3.1-3.7) done. Full suite green (unchanged count vs
PR2 baseline), `lint-imports` green, `forge --help` shows all 16 commands,
CLI surface byte-identical, no circular imports.

### What changed

- Created `src/odoo_forge_cli/commands/maintenance.py`: moved `doctor` and
  `rotate_enterprise_credential` verbatim (bodies unchanged); added
  `register(app: typer.Typer) -> None` binding both via
  `app.command(name=...)` with the exact pre-existing names (`doctor`,
  `rotate-enterprise-credential`). Imports `_composition` and
  `enterprise_credential` (module-qualified: `enterprise_credential.
  _make_enterprise_credential_resolver(...)`, `_composition.
  _doctor_age_key_file()`) and `rotate_enterprise_credential` from
  `odoo_forge_docker.credential_injection` (aliased `_rotate_enterprise_
  credential`, unchanged). No import of `odoo_forge_cli.main` — confirmed
  via `rg`.
- `main.py`: removed the two `@app.command` bodies; added `maintenance` to
  the existing `from odoo_forge_cli.commands import image, maintenance`
  import and a `maintenance.register(app)` call after `image.register(app)`.
  Dropped now-unused imports `run_doctor` (from
  `odoo_forge.credentials.doctor`) and the `rotate_enterprise_credential`
  import from `odoo_forge_docker.credential_injection` (both only used by
  the two moved commands). The `enterprise_credential` bare-name imports
  (`_bind_enterprise_source_provider`, `_bind_enterprise_workspace_provider`,
  `_make_enterprise_credential_resolver`, `_preflight_enterprise_source_
  credential`) and the `__all__` re-export block are UNTOUCHED — both
  `_make_enterprise_credential_resolver` and `_preflight_enterprise_source_
  credential` are still used directly by `lock`/`onboard`, which remain in
  `main.py` until PR5b.
- `main.py` now has 10 `@app.command` decorators (down from 12); the two
  maintenance commands live in `commands/maintenance.py`.

### Test repoint (task 3.4)

`tests/cli/test_doctor.py`: repointed the `main._make_enterprise_
credential_resolver` monkeypatch (3 occurrences) to `enterprise_credential.
_make_enterprise_credential_resolver` — the symbol's owning/definition
module, imported as `from odoo_forge_cli import _composition,
enterprise_credential` (dropped the `main` import, since `main` is no
longer where the patched symbol resolves). The `_composition.
_doctor_age_key_file` patch target was already correct from PR1 and needed
no change. This is a *definition-module* patch target rather than a
*command-module* one — deliberate, since `enterprise_credential.py` is
where `_make_enterprise_credential_resolver` is actually defined, and
`commands/maintenance.py` accesses it module-qualified
(`enterprise_credential._make_enterprise_credential_resolver`), so patching
the definition module is the single canonical target regardless of which
command module calls it (same invariant PR1 established for `_composition`/
`_support`/`_presentation`).

`tests/cli/test_rotate_enterprise_credential.py`: confirmed unchanged (only
patches `odoo_forge_docker.credential_injection.subprocess.run`; only
imports `app` from `main`) — both tests pass unmodified.

### Verification (real output)

```
$ uv run pytest tests/cli/test_doctor.py tests/cli/test_rotate_enterprise_credential.py -v   # RED, post-move pre-repoint
tests/cli/test_doctor.py::test_doctor_fails_and_reports_missing_age_key FAILED
tests/cli/test_doctor.py::test_doctor_fails_and_reports_missing_enterprise_credential PASSED
tests/cli/test_doctor.py::test_doctor_reports_success_on_both_checks FAILED
tests/cli/test_rotate_enterprise_credential.py (both) PASSED
2 failed, 3 passed
```
(The one `test_doctor` case that still passed pre-repoint,
`test_doctor_fails_and_reports_missing_enterprise_credential`, only
asserts on the `_composition._doctor_age_key_file` patch's effect and
`_raising_resolver`'s exception surfacing through `run_doctor` regardless
of which module built the resolver — it did not exercise the stale
`main._make_enterprise_credential_resolver` patch's silent no-op the way
the other two tests' assertions on the SUCCEEDING resolver's marker did.)

```
$ uv run pytest tests/cli/test_doctor.py tests/cli/test_rotate_enterprise_credential.py -v   # GREEN, post-repoint
5 passed
```

```
$ uv run pytest -q   # full suite
901 passed, 17 deselected in 7.69s
```
(Identical to PR1/PR2's post-verification count — zero regressions, zero
new skips.)

```
$ uv run lint-imports
Analyzed 107 files, 339 dependencies.
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Core never imports the docker adapter KEPT
Core never imports the registry adapter KEPT
Contracts: 6 kept, 0 broken.
```

```
$ uv run python -c "import odoo_forge_cli.commands.maintenance; import odoo_forge_cli.main"
no cycle, ok
```

```
$ rg -c "@app.command" src/odoo_forge_cli/main.py
10
```

```
$ uv run forge --help
exit=0, all 16 commands listed unchanged, same order, same help text
$ uv run forge doctor --help
$ uv run forge rotate-enterprise-credential --help
both byte-identical to pre-PR3 output (same options, same help strings)
```

`uv run ruff check` and `uv run ruff format --check` both clean on
`src/odoo_forge_cli/` and `tests/cli/`.

### Diffstat

```
 openspec/changes/split-cli-main/tasks.md |  16 +-
 src/odoo_forge_cli/main.py               |  49 +------
 tests/cli/test_doctor.py                 |  18 +--
 3 files changed (tracked)

New files (not yet tracked by git, awaiting orchestrator commit):
 src/odoo_forge_cli/commands/maintenance.py  (65 lines)
```

## Not started

PR4 (`commands/backend.py`), PR5a/PR5b (`commands/manifest.py`) — all
deferred per PR3-only scope instruction. No further `@app.command` body has
been touched beyond the four image commands + two maintenance commands;
the remaining 10 commands stay verbatim in `main.py`.
