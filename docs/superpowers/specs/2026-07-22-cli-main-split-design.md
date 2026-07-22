# Design: Split `odoo_forge_cli/main.py` by responsibility

- **Date:** 2026-07-22
- **Status:** Approved (design), pending implementation plan
- **Scope:** Internal refactor of the `odoo_forge_cli` package. No user-facing
  behavior change.

## Problem

`src/odoo_forge_cli/main.py` is 896 lines and holds at least three distinct
reasons to change (SRP violation), not merely "too many lines":

1. **Composition root / DI** — seven `_make_*` adapter factories plus
   `_doctor_age_key_file` (lines ~79–125).
2. **Presentation and I/O** — output formatting (`_format_drift`,
   `_format_missing_dependencies`, `_render_validation_errors`) mixed with real
   filesystem I/O (`_read_manifest_data`, `_load_lock`, `_write_lock_atomic`)
   and path resolution (`_resolve_mount_base`, `_host_roots`) (lines ~136–289).
3. **17 Typer commands** across four unrelated families (lines ~295–896).

The module's own sibling (`enterprise_credential.py`) documents that `main`
should "stay a thin Typer presentation layer" — a contract already broken.

## Goals

- Cut by **cohesion**, not by line count.
- CLI behavior **byte-identical**: same command names, options, and output.
- Preserve the entry point `forge = "odoo_forge_cli.main:app"`.
- Preserve the import-linter contract `forbidden_modules = ["odoo_forge_cli"]`
  (nothing outside the package may import it; the internal split is free).

## Non-goals

- No change to CLI command names. Flat, hyphenated names stay
  (`forge image-resolve`, NOT `forge image resolve`). Introducing Typer
  command groups would break existing user scripts for no requested benefit —
  explicitly rejected.
- No behavior/feature changes. No unrelated refactoring.

## Target structure

```
odoo_forge_cli/
  main.py            app = Typer() + callback + register(app) per module   (~60 lines)
  _composition.py    _make_* factories + _doctor_age_key_file              (DI / composition root)
  _presentation.py   _format_drift, _format_missing_dependencies, _render_validation_errors
  _support.py        _resolve_mount_base, _host_roots, _read_manifest_data,
                     _load_lock, _write_lock_atomic, _check_module_dependencies
  commands/
    image.py         image-resolve, image-publish, image-pull, image-exists
    backend.py       run, status, stop, logs, exec  (+ _derive_ref)
    manifest.py      validate, onboard, lock, unlock, project
    maintenance.py   doctor, rotate-enterprise-credential
```

Target constraints: `main.py` ≤ ~80 lines; no module > ~250 lines.

## Registration mechanism (avoids circular imports)

Each `commands/*.py` exposes:

```python
def register(app: typer.Typer) -> None:
    app.command(name="image-resolve")(image_resolve)
    ...
```

`main.py` creates the single `app`, then calls each module's `register(app)`.
No command module imports from `main`, so there is no import cycle. Command
functions and their helpers live in their command module; shared helpers are
imported from `_support.py` / `_presentation.py` / `_composition.py`.

## Test strategy (the real risk)

27 test files touch the CLI; 21 import from `main`.

- **Unchanged:** tests that drive the CLI through Typer's `CliRunner` against
  `app`. `app` stays in `main.py` with every command registered, so these keep
  working verbatim.
- **Updated:** tests that (a) import internal symbols directly
  (`_resolve_mount_base`, `_make_backend_provider`, `plan_backend`, …), or
  (b) `monkeypatch` `odoo_forge_cli.main.<symbol>`. These are repointed to the
  new module where the symbol now lives.

**No re-export facade.** Re-exporting a moved symbol from `main` would let a
`monkeypatch.setattr("odoo_forge_cli.main.X", ...)` silently no-op (it patches
`main`'s binding, not the destination module's real reference). Patch targets
are updated to the true new location instead.

## Delivery: chained PRs (lowest risk first)

1. **PR1** — extract `_composition.py` + `_presentation.py` + `_support.py`.
   No commands move. Update the few tests importing those internals.
2. **PR2** — `commands/image.py` (most isolated family).
3. **PR3** — `commands/maintenance.py`.
4. **PR4** — `commands/backend.py` (heaviest monkeypatch surface).
5. **PR5** — `commands/manifest.py`; `main.py` becomes thin.

Each PR: behavior-preserving, full suite green before merge, TDD where new
seams warrant a characterization test.

## Success criteria

- `forge` CLI byte-identical (names, options, output) — verified by the
  existing `CliRunner` suite staying green unmodified.
- `main.py` ≤ ~80 lines; no new module > ~250 lines.
- Full test suite green after **each** PR.
- Import-linter contract still satisfied.
- No circular imports (import smoke check per PR).

## Risks & mitigations

- **Silent monkeypatch drift** → audit every `monkeypatch.setattr` /
  `patch("odoo_forge_cli.main...")` and repoint; no facade.
- **Circular import via registration** → `register(app)` pattern; command
  modules never import `main`.
- **Hidden cross-command helper coupling** → `_derive_ref` travels with
  `backend.py`; shared-only helpers land in `_support.py`.
