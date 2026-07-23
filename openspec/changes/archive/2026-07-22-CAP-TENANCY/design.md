# Design: CAP-TENANCY

## Technical Approach

Contract-first and provider-neutral, mirroring the accepted `CAP-RESOURCE-OWNERSHIP` precedent (one isolated core package of pure value types + a typed error hierarchy, no adapter, no runtime integration). Per authoritative user decisions, v1 ships **pure types + errors only**: `TenantId`, `ProjectScope`, `TenantScopedOwnership`, and a `QuotaAuthority` marker, plus a normative `TenancyError` tree. **No `tenancy_provider` port in v1** — the consumer seam is deferred until the first adapter appears (proposal Q2 resolved to types-only). Ownership composition reuses the existing `ResourceOwnership` StrEnum from `resource_ownership.types` via read-only import — reuse, never redefine.

Types follow the shipped `resource_ownership/types.py` idiom exactly: frozen pydantic `BaseModel` (`ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)`) via a private `_TenancyValue` base. Errors follow the `durable_operations/errors.py` idiom: plain `Exception` subclasses under one base, attributes carried on the instance.

**Parallel-safety boundary:** this change touches ONLY `src/odoo_forge/tenancy/{__init__,types,errors}.py` and `tests/tenancy/**`. It MUST NOT modify `pyproject.toml` (new sub-package lives under the already-registered `src/odoo_forge` package — no packaging edit needed), `src/odoo_forge/manifest/schema.py`, `src/odoo_forge/credentials/*`, `src/odoo_forge_cli/*`, or any pipeline path. It does NOT create `ports/tenancy_provider.py`. Importing `resource_ownership.types.ResourceOwnership` is read-only and does not touch that file; the parallel worktree is `PORT-PIPELINE`, so there is zero collision.

## Architecture Decisions

| Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|
| v1 surface | Pure `types.py` + `errors.py` only | Ship a `tenancy_provider` Protocol port now | User decision (Q2). No consumer exists in v1; a port with no adapter is speculative. Add the seam when the first adapter lands. |
| Tenant identity | `TenantId(value: str)` frozen value type, `min_length=1` | Bare `tenant_id: str` string alias | A first-class canonical type prevents downstream from redefining project/env/account as a peer tenancy unit (spec: Canonical Tenant Identity). |
| Subordinate scope | `ProjectScope{tenant: TenantId, project_id: str}` — tenant field is required | `project_id: str` with tenant optional | Enforces "project MUST NOT exist without tenant association" at the type level; project is the ONLY v1 subordinate scope. |
| Ownership composition | `TenantScopedOwnership{tenant, project?, ownership: ResourceOwnership}` reusing the imported enum | Re-declare `created/adopted/external` here | "Defined exactly once" — `CAP-RESOURCE-OWNERSHIP` owns the label set; compose, never duplicate. |
| Quota authority | `QuotaAuthority{tenant: TenantId}` marker type with NO dimension fields | Enumerate concrete dimensions (storage, env count, concurrency) | User decision (Q1): declare the authority anchor exactly once; defer dimensions to consumers. The type's mere existence at `CAP-TENANCY` establishes the single authority. |
| Error model | `TenancyError` base + typed subclasses on the instance | Return codes / string sentinels | Matches `durable_operations/errors.py`; typed, redacted, catchable per failure mode. |
| Operational classifications | PROD/QA/DEV modeled as NOTHING here | Add an env-family type | Spec forbids env family as a tenancy unit in v1; absence is the contract. |

## Conceptual Model

```text
TenantId(value)                      -- canonical customer/client identifier
ProjectScope(tenant, project_id)     -- only v1 subordinate scope; tenant required
TenantScopedOwnership                -- composition, reuses CAP-RESOURCE-OWNERSHIP
  tenant: TenantId
  project: ProjectScope | None
  ownership: ResourceOwnership        (created|adopted|external, imported)
QuotaAuthority(tenant)               -- authority anchor; NO dimensions in v1
```

## File Changes

| File | Action | Description |
|---|---|---|
| `openspec/changes/CAP-TENANCY/design.md` | Create | This design. |
| `src/odoo_forge/tenancy/__init__.py` | Create | Re-export the four value types + error tree; `__all__` sorted. |
| `src/odoo_forge/tenancy/types.py` | Create | `_TenancyValue` base + `TenantId`, `ProjectScope`, `TenantScopedOwnership`, `QuotaAuthority`. |
| `src/odoo_forge/tenancy/errors.py` | Create | `TenancyError` + `UnknownTenantError`, `ProjectWithoutTenantError`, `CrossTenantAccessError`, `QuotaExceededError` (declared; enforcement deferred). |
| `tests/tenancy/__init__.py` | Create | Test package marker. |
| `tests/tenancy/test_types.py` | Create | Value-type contract tests. |
| `tests/tenancy/test_errors.py` | Create | Error-hierarchy contract tests. |

## Interfaces / Contracts

Quota authority is expressed WITHOUT enumerating dimensions — the type is a tenant-keyed anchor whose presence at this package is the "defined exactly once" evidence:

```python
class QuotaAuthority(_TenancyValue):
    """Single tenant-level quota authority anchor. v1 declares the authority;
    concrete dimensions are deferred to a future revision, never to consumers."""
    tenant: TenantId
```

## Testing Strategy (RED first — strict TDD)

| Layer | What to prove | Approach |
|---|---|---|
| Unit | `TenantId`/`ProjectScope` frozen, `extra="forbid"`, `min_length` rejects empty; `ProjectScope` requires `tenant` | Pure pytest value-type tests |
| Unit | `TenantScopedOwnership` reuses the imported `ResourceOwnership` enum (no local redefinition) | Assert enum identity `is` |
| Unit | `QuotaAuthority` carries only `tenant`, exposes no dimension fields | Field-set assertion |
| Contract | Each error subclasses `TenancyError`; instance attributes preserved | Hierarchy + attribute tests |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Pure-core value types and exception classes only.

## Migration / Rollout

No runtime migration. Single small PR: contract only, no adapter, no runtime integration — well under the 400-line budget. Rollback reverts the `tenancy/` package + tests and re-blocks the 5 downstream items; parallel `PORT-PIPELINE` is unaffected (disjoint paths).

## Open Questions

None. All proposal questions resolved by authoritative user decisions (pure types + errors, quota authority declared without dimensions, tenant = customer/client `tenant_id`, project sole subordinate scope).
