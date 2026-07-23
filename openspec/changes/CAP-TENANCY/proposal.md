# Proposal: CAP-TENANCY

## Intent

Establish `CAP-TENANCY` as the contract-first, provider-neutral platform capability that gives every downstream item one answer for tenant identity, subordinate scope, isolation, ownership composition, and quota authority. The gating decision `DT` is DECIDED (2026-07-11): the tenant is the **customer/client**, keyed by a stable `tenant_id`. This change turns that decision plus the drafted `openspec/specs/tenancy-contract/spec.md` into an accepted proposal, closing readiness gate `AC-CAP-TENANCY-READY` so 5 blocked downstream items can proceed to spec/design: `SP-CONTROL-PLANE-AUTHORITY`, `SP-REMOTE-DEPLOYMENT`, `SP-ENVIRONMENT-REQUESTS`, `CHG-FIRST-IDENTITY-ADAPTER`, `CHG-FIRST-REMOTE-ADAPTER`. Contract only — no adapter, no runtime integration.

## Scope

### In Scope
- New package `src/odoo_forge/tenancy/` (`__init__.py`, `types.py`, `errors.py`) defining tenant identity/scope value types and tenancy error types.
- Optional consumer seam: new `src/odoo_forge/ports/tenancy_provider.py` (only if the contract needs a port surface).
- New tests under `tests/tenancy/` (and `tests/ports/test_tenancy_provider.py` if the port is added).
- Change artifacts under `openspec/changes/CAP-TENANCY/`; canonical capability spec at `openspec/specs/tenancy-contract/spec.md` (read; not relocated here).
- Acceptance evidence sufficient to satisfy `AC-CAP-TENANCY-READY`.

### Out of Scope
- No control-plane runtime authority (`SP-CONTROL-PLANE-AUTHORITY`).
- No remote deployment / environment-request workflow logic.
- No identity or remote adapter implementation.
- No quota enforcement engine — quota authority is *declared once* here, not enforced.
- No new subordinate scope beyond `project` in v1; PROD/QA/DEV stay operational classifications, not tenancy units.

## Parallel-Safety Non-Collision Boundary

Runs in parallel with `PORT-PIPELINE` in another worktree. To guarantee zero collision, CAP-TENANCY touches ONLY: `src/odoo_forge/tenancy/**` (new), `src/odoo_forge/ports/tenancy_provider.py` (new, optional), `tests/tenancy/**` and `tests/ports/test_tenancy_provider.py` (new), and its own `openspec/changes/CAP-TENANCY/` artifacts. It MUST NOT modify `pyproject.toml` (stay under the registered `src/odoo_forge` package — no new top-level `odoo_forge_*` package), `src/odoo_forge/manifest/schema.py`, `src/odoo_forge/credentials/*`, `src/odoo_forge_cli/*`, or `src/odoo_forge/ports/pipeline_provider.py`.

## Capabilities

### New Capabilities
- `tenancy-contract`: canonical tenant identity (`tenant_id`), project as the only v1 subordinate scope, minimum isolation boundary, ownership composition (`created`/`adopted`/`external`), quota authority defined exactly once, and the consumer/no-redefine boundary.

### Modified Capabilities
- None.

## Approach

Contract-first, matching the accepted `CAP-RESOURCE-OWNERSHIP` precedent (one isolated contract: new `src/odoo_forge/<pkg>/` + matching tests, no shared-file churn). Author tenant identity, scope, ownership composition, and quota authority exactly once as pure value/error types; expose a thin optional `tenancy_provider` port as the consumer seam. Downstream items consume, never redefine.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/tenancy/` | New | Tenant identity/scope types + errors |
| `src/odoo_forge/ports/tenancy_provider.py` | New (optional) | Consumer seam for the contract |
| `tests/tenancy/`, `tests/ports/test_tenancy_provider.py` | New | Contract tests |
| `openspec/changes/CAP-TENANCY/` | New | Proposal + follow-on artifacts |
| `openspec/specs/tenancy-contract/spec.md` | Read only | Existing draft; merged at archive |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope bleed into control-plane / quota enforcement | Med | Contract only; declare quota authority, defer enforcement |
| Provider leakage into "neutral" contract | Med | Pure value types; describe isolation outcomes, not mechanisms |
| Collision with parallel `PORT-PIPELINE` | Low | Disjoint path boundary above; forbidden-file list |
| Redefining `project`/env family as tenancy | Low | v1 fixes `project` as sole subordinate scope |

## Rollback Plan

Revert the `CAP-TENANCY` change artifacts and the new `src/odoo_forge/tenancy/` package/tests; keep the 5 downstream items blocked until a corrected contract is approved. No runtime rollback — this introduces planning authority and pure types, not product behavior. No shared files are touched, so parallel `PORT-PIPELINE` is unaffected.

## Dependencies

- `openspec/specs/tenancy-contract/spec.md` (existing draft)
- Decided gating decision `DT` (tenant = customer/client, 2026-07-11)
- `docs/specs/platform/portfolio.json` (CAP-TENANCY node)
- Precedent: archived `CAP-RESOURCE-OWNERSHIP`

## Success Criteria

- [ ] Contract fixes `tenant_id` as the canonical customer/client identifier, `project` as the only v1 subordinate scope, PROD/QA/DEV as operational classifications.
- [ ] Ownership composition (`created`/`adopted`/`external`) and quota authority are each defined exactly once.
- [ ] `tenancy-contract` types (and optional `tenancy_provider` port) live only under the disjoint path boundary; no forbidden file is touched.
- [ ] `AC-CAP-TENANCY-READY` evidence unblocks the 5 downstream items to spec/design.

## Proposal Question Round

These sharpen the contract before spec/design; answer, skip, correct, or request a second round.

1. **Quota shape:** must the v1 contract name concrete quota dimensions (e.g. environment count, storage, concurrency), or only assert "quota authority lives here" and defer dimensions to consumers?
2. **Port necessity:** is a `tenancy_provider` port needed in v1 (a consumer seam / resolver), or should v1 ship pure `types.py` + `errors.py` only and add the port when the first adapter appears?
3. **Tenant attribution timing:** must every tenant-scoped resource carry a `tenant_id` at creation, or may `external`/pre-adoption resources stay tenant-unattributed until adopted?
4. **Error surface:** which failure modes are normative here (unknown tenant, project-without-tenant, cross-tenant access, quota-exceeded), versus left to consuming capabilities?

Assumptions pending review (used if unanswered): quota authority is *declared* here with dimensions deferred (Q1); v1 ships pure types + errors, port added only if the contract needs a consumer seam (Q2); `external`/pre-adoption resources may be tenant-unattributed until adopted (Q3); errors cover unknown-tenant, project-without-tenant, and cross-tenant-access, with quota-exceeded declared but enforcement deferred (Q4).
