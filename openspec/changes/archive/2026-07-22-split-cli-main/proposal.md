# Proposal: Split `odoo_forge_cli/main.py` by responsibility

## Intent

`src/odoo_forge_cli/main.py` is 896 lines with three distinct reasons to change (SRP violation): composition/DI factories, presentation + I/O + path helpers, and 17 Typer commands across four unrelated families. The sibling `enterprise_credential.py` already documents that `main` should "stay a thin Typer presentation layer" — a contract now broken. Split by cohesion so each unit has one reason to change, with zero user-facing behavior change.

## Scope

### In Scope
- `main.py` → thin: `app` + callback + `register(app)` call per command module (≤ ~80 lines).
- `_composition.py`: `_make_*` factories + `_doctor_age_key_file`.
- `_presentation.py`: `_format_drift`, `_format_missing_dependencies`, `_render_validation_errors`.
- `_support.py`: `_resolve_mount_base`, `_host_roots`, `_read_manifest_data`, `_load_lock`, `_write_lock_atomic`, `_check_module_dependencies`.
- `commands/{image,backend,manifest,maintenance}.py` — each exposes `register(app)`; `_derive_ref` travels with `backend.py`.
- Repoint every test that imports internals or `monkeypatch`es `odoo_forge_cli.main.<symbol>` to the symbol's new home.

### Out of Scope
- CLI command names, options, or output — byte-identical (flat hyphenated names stay: `forge image-resolve`, NOT groups).
- Any behavior/feature change; any unrelated refactoring.
- A re-export facade (would let moved-symbol monkeypatches silently no-op).

## Capabilities

### New Capabilities
None — internal refactor, no spec-level behavior introduced.

### Modified Capabilities
None — CLI contract unchanged.

## Approach

`main.py` creates one `app`, then calls each command module's `register(app)`. No command module imports `main` → no cycle. Shared helpers imported from `_support`/`_presentation`/`_composition`. Delivered as 5 chained PRs, lowest-risk-first: PR1 helpers, PR2 `commands/image`, PR3 `commands/maintenance`, PR4 `commands/backend` (heaviest monkeypatch surface), PR5 `commands/manifest` + thin `main`. Full suite green after each PR.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_cli/main.py` | Modified | Reduced to thin app + registration |
| `src/odoo_forge_cli/_composition.py`, `_presentation.py`, `_support.py` | New | Extracted helpers |
| `src/odoo_forge_cli/commands/*.py` | New | Command families + `register()` |
| CLI test suite (27 files) | Modified | Repointed patch/import targets |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Silent monkeypatch drift | High | Audit every `patch("odoo_forge_cli.main...")`, repoint; no facade |
| Circular import via registration | Med | `register(app)` pattern; commands never import `main` |
| Hidden cross-command helper coupling | Med | Shared-only helpers → `_support`; owned helpers travel with their command |

## Rollback Plan

Each PR is independent and behavior-preserving; revert the offending PR's merge commit. `git` history keeps the pre-split `main.py` intact until PR5.

## Dependencies

- Entry point `forge = "odoo_forge_cli.main:app"` preserved.
- Import-linter contract `forbidden_modules = ["odoo_forge_cli"]` stays satisfied (internal split is unconstrained).

## Success Criteria

- [ ] `forge` CLI byte-identical (existing `CliRunner` suite green, unmodified).
- [ ] `main.py` ≤ ~80 lines; no module > ~250 lines.
- [ ] Full suite green after each PR; no circular imports (smoke check).
- [ ] `lint-imports` contract still passes.
