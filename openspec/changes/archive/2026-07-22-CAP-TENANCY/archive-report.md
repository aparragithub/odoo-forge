# Archive Report: CAP-TENANCY

## Result

**PASS** — verified with 0 CRITICAL, 0 WARNING, 2 SUGGESTION (Engram verify-report id 3283).
Implementation committed at `8ef415a` on branch `sdd/cap-tenancy`. All 22 tasks marked complete (Engram tasks id 3279).

## Spec Sync Outcome

Canonical spec `openspec/specs/tenancy-contract/spec.md` (pre-existing 8-requirement DRAFT, 135 lines) reconciled against the change's formalized delta `openspec/changes/CAP-TENANCY/specs/tenancy-contract/spec.md` (6 ADDED requirements, 99 lines, Engram spec id 3275).

Reconciliation applied:
- **Superseded/replaced (draft → formalized implementation-verified text):**
  - `Canonical Tenant Identity` → `Canonical Tenant Identity Type` (adds concrete pure-value-type + module location `src/odoo_forge/tenancy/`)
  - `Project Is the Only Normative Subordinate Scope in v1` → `Project Is the Sole v1 Subordinate Scope` (adds concrete constructor-failure behavior)
  - `Minimum Tenant Isolation Contract` → `Isolation Boundary Declaration` (sharper outcome-only, provider-neutral wording)
  - `Ownership Semantics Compose With Tenant Authority` → `Ownership Composition Types` (adds unattributed-pre-adoption scenario for `external`)
  - `Quota Authority Is Defined Exactly Once` → `Quota Authority Declared Exactly Once` (explicitly excludes concrete quota dimensions)
- **Added (new, not previously in canonical spec):**
  - `Normative Tenancy Error Types` (unknown tenant, project-without-tenant, cross-tenant access, quota-exceeded reserved) under `src/odoo_forge/tenancy/errors.py`
- **Preserved unchanged (draft requirements not contradicted or superseded by the delta):**
  - `Operational Classifications Do Not Define Tenancy`
  - `Downstream Consumers Must Consume and Must Not Redefine`
  - `Acceptance Evidence for Tenancy Readiness` (updated only to reference the new error-types requirement in its evidence list; no new requirement introduced)

Result: 9 requirements total, no duplicate or conflicting requirement names, no requirements lost, no requirements introduced beyond what the delta specified.

## Delivered Contract Summary

`CAP-TENANCY` v1 ships as a pure, provider-neutral contract capability:
- **Types** (`src/odoo_forge/tenancy/types.py`): `TenantId` (frozen, `min_length=1`), `ProjectScope` (requires `TenantId`, non-optional), `TenantScopedOwnership` (composes with imported `ResourceOwnership` by reference, does not redefine it), `QuotaAuthority` (marker type — `tenant` field only, no quota dimensions).
- **Errors** (`src/odoo_forge/tenancy/errors.py`): `TenancyError` hierarchy — unknown tenant, project-without-tenant, cross-tenant access, quota-exceeded (reserved, enforcement deferred).
- **No consumer port**: `tenancy_provider` port intentionally NOT created — per user decision Q2, v1 is types + errors only.
- **Quota authority-only**: `QuotaAuthority` declares authority location exclusively; no quota dimensions (counts/storage/concurrency) are defined at this capability.

Verified: 15/15 tenancy tests pass, full suite 916 passed / 17 deselected (no regression), `lint-imports` contracts 6 kept / 0 broken, 100% line coverage on changed files.

## Source Artifact Traceability (Engram observation IDs)

| Artifact | Engram ID |
|---|---|
| Proposal | 3273 |
| Delta Spec | 3275 |
| Design | 3277 |
| Tasks | 3279 |
| Verify Report | 3283 |

## Archival Note

This report was written with the change folder still active at `openspec/changes/CAP-TENANCY/`. The archive executor performing this phase has no Bash tool and did NOT move, rename, or delete any folder. Moving `openspec/changes/CAP-TENANCY/` to the archive location is the orchestrator's responsibility via `git mv`, to be performed after this report is written.
