# Tasks: CAP-TENANCY

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~180-260 (6 new files, no edits to existing files) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Ship `tenancy` pure-contract package (types + errors + tests) | PR 1 | `uv run pytest tests/tenancy/` | N/A — pure value types, no runtime/CLI/adapter surface | Delete `src/odoo_forge/tenancy/` + `tests/tenancy/`; no other file touched |

## Phase 1: RED — Failing Tests First

- [ ] 1.1 Create `tests/tenancy/__init__.py` (empty test package marker).
- [ ] 1.2 In `tests/tenancy/test_types.py`, write failing test: `TenantId(value="t1")` is frozen, `extra="forbid"` rejects unknown fields.
- [ ] 1.3 In `tests/tenancy/test_types.py`, write failing test: `TenantId(value="")` raises validation error (`min_length=1`).
- [ ] 1.4 In `tests/tenancy/test_types.py`, write failing test: `ProjectScope(project_id="p1")` without `tenant` raises validation error (tenant required).
- [ ] 1.5 In `tests/tenancy/test_types.py`, write failing test: `ProjectScope(tenant=TenantId(value="t1"), project_id="p1")` constructs successfully.
- [ ] 1.6 In `tests/tenancy/test_types.py`, write failing test: `TenantScopedOwnership.ownership` field type `is` the imported `resource_ownership.types.ResourceOwnership` enum (identity assertion, no local redefinition).
- [ ] 1.7 In `tests/tenancy/test_types.py`, write failing test: `TenantScopedOwnership` accepts `project=None` (external/unattributed case) and a `ProjectScope` value.
- [ ] 1.8 In `tests/tenancy/test_types.py`, write failing test: `QuotaAuthority(tenant=TenantId(value="t1"))` exposes exactly the field set `{"tenant"}` — no dimension fields.
- [ ] 1.9 In `tests/tenancy/test_errors.py`, write failing test: `UnknownTenantError`, `ProjectWithoutTenantError`, `CrossTenantAccessError`, `QuotaExceededError` all subclass `TenancyError`.
- [ ] 1.10 In `tests/tenancy/test_errors.py`, write failing test: each error preserves constructor attributes on the instance (e.g. `tenant_id`).
- [ ] 1.11 Run `uv run pytest tests/tenancy/` and confirm all new tests fail with `ModuleNotFoundError`/`ImportError` (RED confirmed).

## Phase 2: GREEN — Implement Contract

- [ ] 2.1 Create `src/odoo_forge/tenancy/types.py`: private `_TenancyValue` base (`ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)`), mirroring `resource_ownership/types.py`.
- [ ] 2.2 Add `TenantId(_TenancyValue)` with `value: str` (`min_length=1`) to `types.py`.
- [ ] 2.3 Add `ProjectScope(_TenancyValue)` with `tenant: TenantId` (required) and `project_id: str` to `types.py`.
- [ ] 2.4 Add `TenantScopedOwnership(_TenancyValue)` with `tenant: TenantId`, `project: ProjectScope | None`, `ownership: ResourceOwnership` — import `ResourceOwnership` read-only from `odoo_forge.resource_ownership.types`.
- [ ] 2.5 Add `QuotaAuthority(_TenancyValue)` with only `tenant: TenantId` and the authority-anchor docstring from design.md.
- [ ] 2.6 Create `src/odoo_forge/tenancy/errors.py`: `TenancyError(Exception)` base, then `UnknownTenantError`, `ProjectWithoutTenantError`, `CrossTenantAccessError`, `QuotaExceededError`, each carrying relevant attributes on the instance (mirroring `durable_operations/errors.py`).
- [ ] 2.7 Create `src/odoo_forge/tenancy/__init__.py` re-exporting `TenantId`, `ProjectScope`, `TenantScopedOwnership`, `QuotaAuthority`, `TenancyError`, `UnknownTenantError`, `ProjectWithoutTenantError`, `CrossTenantAccessError`, `QuotaExceededError` with a sorted `__all__`.
- [ ] 2.8 Run `uv run pytest tests/tenancy/` and confirm all tests pass (GREEN).

## Phase 3: REFACTOR — Clean Up

- [ ] 3.1 Review `types.py`/`errors.py` docstrings against design.md wording (Canonical Tenant Identity, sole subordinate scope, ownership composition, quota authority declared once) — tighten without changing behavior.
- [ ] 3.2 Confirm no duplicate `ResourceOwnership` label definitions exist; the import in `types.py` is the only reference.
- [ ] 3.3 Re-run `uv run pytest tests/tenancy/` to confirm refactor kept tests green.

## Phase 4: Verification

- [ ] 4.1 Run `uv run pytest tests/tenancy/` — full suite green.
- [ ] 4.2 Run `uv run lint-imports` — confirm no import-boundary violations (tenancy package stays pure-core, no provider/adapter/CLI import).
- [ ] 4.3 Diff-review: confirm ONLY `src/odoo_forge/tenancy/{__init__,types,errors}.py` and `tests/tenancy/**` changed — no edits to `pyproject.toml`, `manifest/schema.py`, `credentials/*`, or `odoo_forge_cli/*`.
