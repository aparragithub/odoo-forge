# Proposal: PORT-IDENTITY — Provider-Neutral Identity Port

## Intent

`odoo-forge` has no structural seam for authenticating platform users against an
organization identity provider (gap G4: "No identity port exists"). SP-5 frames the
control plane's need: reuse an existing organization IdP to authenticate access and
map authenticated identities onto platform roles, storing only role mappings — never
credentials or a mirrored user directory. We introduce the provider-neutral identity
PORT CONTRACT now so downstream auth/RBAC work can depend on a stable abstract
interface without committing to a specific IdP. Decisions DP ("one adapter bound
globally at init") and DG ("independent roadmap enablers") are DECIDED and shape this
contract. The concrete adapter (`CHG-FIRST-IDENTITY-ADAPTER`) is gated by the
unresolved decision `DPROV-IDP` (which IdP is first) — so only the contract is in play.

## Scope

### In Scope
- NEW `src/odoo_forge/ports/identity_provider.py` — `IdentityProvider` structural port
  (`Protocol`, `runtime_checkable`), mirroring `pipeline_provider.py` style: module
  docstring, `from __future__ import annotations`, `TYPE_CHECKING` domain-type imports,
  `__all__`. No adapter import.
- NEW provider-neutral domain types under `src/odoo_forge/identity/` (new subpackage:
  `__init__.py` + `types.py`) — IdP-agnostic authentication request / identity claims /
  session-or-token reference vocabulary only.
- NEW conformance/neutrality test under `tests/ports/` mirroring the pipeline port test
  (structural `isinstance` pass, negative non-conforming case, neutrality-denylist and
  no-adapter-import assertions).

### Out of Scope (non-goals)
- NO concrete adapter — `CHG-FIRST-IDENTITY-ADAPTER` stays gated on `DPROV-IDP`.
- NO IdP-vendor-specific names, protocol details, or handshake wiring (GitHub / GitLab /
  Google / OIDC-vendor specifics). The contract MUST stay provider-neutral.
- NO role model, authorization enforcement, session storage, CLI wiring, or credential
  persistence — those are downstream SP-5 work, not this port.
- Exact neutral method surface is deferred to the design phase.

## Non-Collision Boundary

File-disjoint from all other work. Touches ONLY the disjoint new paths above, all inside
this worktree. MUST NOT modify `pyproject.toml`, `src/odoo_forge/ports/__init__.py`
(EMPTY, stays empty — no re-exports), or any existing port/module.

## Capabilities

### New Capabilities
- `identity-provider`: provider-neutral identity/authentication port contract — abstract
  interface plus IdP-agnostic domain types and a conformance/neutrality test.

### Modified Capabilities
- None.

## Approach

Add a `runtime_checkable` `Protocol` for `IdentityProvider` following the existing port
pattern (structural, interface-only, no adapter import). Express methods and domain types
in provider-neutral vocabulary (authenticate → claims; identity/session reference). Prove
satisfiability with a structural fake in the port test; assert the neutrality boundary and
absence of adapter imports via source-scan tests. The design phase fixes the exact method
surface; this proposal fixes only intent and boundaries.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/ports/identity_provider.py` | New | Port interface |
| `src/odoo_forge/identity/` | New | Neutral domain types subpackage |
| `tests/ports/test_identity_provider.py` | New | Conformance/neutrality test |
| `openspec/changes/port-identity/` | New | SDD artifacts |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Contract leaks IdP-vendor assumptions | Med | Neutral vocabulary; source-scan denylist test |
| Over-building ahead of `DPROV-IDP` | Med | Contract-only scope; adapter explicit non-goal |
| Credential/user-data concepts creep in | Low | Mappings/claims only; SP-5 "no credentials" invariant |

## Rollback Plan

Delete `src/odoo_forge/ports/identity_provider.py`, `src/odoo_forge/identity/`, and
`tests/ports/test_identity_provider.py`. No shared file touched — revert is isolated and
leaves no dangling references.

## Dependencies

- `DPROV-IDP` decision — required only for the downstream adapter, NOT for this contract.

## Success Criteria

- [ ] `IdentityProvider` port exists, interface-only, mirroring existing port style.
- [ ] Conformance test passes (`uv run pytest tests/ports/test_identity_provider.py`).
- [ ] No IdP-vendor-specific names/choices anywhere in the contract.
- [ ] No credentials, passwords, or user-directory concepts in the contract.
- [ ] No file outside the disjoint allowlist is modified.
- [ ] Delivers as a single small PR (contract only).
