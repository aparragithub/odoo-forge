# Apply Progress: CAP-TENANCY

## Status: Complete (all 22 tasks done, single PR)

Strict TDD (RED → GREEN → REFACTOR) followed throughout.

### RED
- Wrote `tests/tenancy/test_types.py` (7 tests) and `tests/tenancy/test_errors.py` (8 tests)
  before any implementation existed.
- Confirmed failure: `uv run pytest tests/tenancy/` failed at collection with
  `ImportError: cannot import name 'ProjectScope'/'CrossTenantAccessError' from 'odoo_forge.tenancy'`.

### GREEN
- Created `src/odoo_forge/tenancy/types.py`: `_TenancyValue` base (frozen, `extra="forbid"`,
  `hide_input_in_errors=True`), `TenantId` (`min_length=1`), `ProjectScope` (tenant required),
  `TenantScopedOwnership` (imports `ResourceOwnership` read-only from
  `odoo_forge.resource_ownership.types`, no redefinition), `QuotaAuthority` (tenant-only marker).
- Created `src/odoo_forge/tenancy/errors.py`: `TenancyError` base +
  `UnknownTenantError`, `ProjectWithoutTenantError`, `CrossTenantAccessError`,
  `QuotaExceededError`, mirroring `durable_operations/errors.py` idiom (attributes on instance).
- Created `src/odoo_forge/tenancy/__init__.py` re-exporting all 9 names, sorted `__all__`.
- `uv run pytest tests/tenancy/` — 15 passed.

### REFACTOR
- Docstrings tightened to match design.md wording (canonical identity, sole subordinate
  scope, composition-not-redefinition, quota authority declared once).
- Verified `ResourceOwnership` is imported once in `types.py`, no duplicate definition.
- Re-ran `uv run pytest tests/tenancy/` — still 15 passed.

## Verification (real output)

- `uv run pytest tests/tenancy/` → 15 passed.
- `uv run pytest` (full suite) → 916 passed, 17 deselected, 1 warning.
- `uv run lint-imports` → Contracts: 6 kept, 0 broken.
- `git status --short` → only `?? src/odoo_forge/tenancy/` and `?? tests/tenancy/` (untracked,
  new directories). No forbidden path (`pyproject.toml`, `manifest/schema.py`, `credentials/*`,
  `odoo_forge_cli/*`, `ports/`, `pipeline/`) touched.

## Parallel-safety confirmation

Disjoint from concurrent `PORT-PIPELINE` worktree: only new files under
`src/odoo_forge/tenancy/` and `tests/tenancy/` were created; `resource_ownership/types.py`
was imported read-only, never modified.
