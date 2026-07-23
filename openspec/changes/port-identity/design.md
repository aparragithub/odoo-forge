# Design: PORT-IDENTITY — Provider-Neutral Identity Port

## Technical Approach

Add a structural, interface-only identity seam that is a direct twin of the archived
`PipelineProvider` port. The core exposes a `runtime_checkable` `Protocol`
(`IdentityProvider`) whose methods speak only in neutral pydantic domain types living in a
sibling `odoo_forge.identity` subpackage. `from __future__ import annotations` keeps every
annotation a lazy string, so the port never imports the types module at runtime and never
imports any adapter. This realizes SP-5's "IdP is the orchestra; the server decides what each
role may do": the port returns verified claims; role mapping and persistence are downstream.
Zero I/O, zero vendor vocabulary. Adapter selection stays gated on `DPROV-IDP`.

## Architecture Decisions

### Decision: Two-phase handshake abstracted as `begin` + `verify`, plus `resolve`
| Option | Tradeoff | Decision |
|--------|----------|----------|
| Single `verify(assertion)` | Minimal, but no neutral way to *start* a login | Rejected |
| `begin` + `verify` + `resolve` | Mirrors real IdP flows (initiate → complete → re-establish) without redirect/device specifics | **Chosen** |
| Add `refresh`/`revoke` | Session-lifecycle creep ahead of need | Rejected (deferred to adapter era) |

**Rationale**: Every org-IdP flow (redirect, device code, PKCE) reduces to: start an attempt,
then exchange an opaque provider artifact for verified claims. `resolve` is required because
SP-5 stores *only* session/token references ("pointers, not copies") — the port must turn a
stored reference back into a principal, or the reference is useless. Three methods matches the
pipeline port's proven cardinality.

### Decision: Neutral names — no OIDC/JWT/SSO in the surface
**Choice**: `begin`/`verify`/`resolve`; types named around request / challenge / assertion /
principal / session-reference. **Alternatives**: OIDC-flavored `authorize`/`token`/`userinfo`.
**Rationale**: The proposal and SP-5 forbid vendor/protocol leakage. Opaque `value`/`payload`
strings carry provider artifacts without naming them (code, JWT, SAML, bearer).

### Decision: Claims returned, never persisted; no credentials in any type
**Choice**: `AuthenticatedPrincipal.claims: dict[str, str]` is transient output only.
**Rationale**: SP-5 invariant — store role mappings + session references, never passwords or a
mirrored directory. The port carries claims to the mapper; persistence policy is downstream.

## Data Flow

    caller ──begin(AuthenticationRequest)──▶ IdentityProvider ──▶ AuthenticationChallenge
      │                                                                    │ (relayed to IdP)
      ▼                                                                    ▼
    caller ──verify(IdentityAssertion)──▶ IdentityProvider ──▶ AuthenticatedPrincipal(subject, claims, session)
      │                                                                    │
      └── stores SessionRef only ──resolve(SessionRef)──▶ AuthenticatedPrincipal

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge/ports/identity_provider.py` | Create | `runtime_checkable Protocol IdentityProvider`; `__future__` + `TYPE_CHECKING` type imports; `__all__`; no adapter import |
| `src/odoo_forge/identity/__init__.py` | Create | Empty package marker (mirrors empty `pipeline/__init__.py`) |
| `src/odoo_forge/identity/types.py` | Create | Neutral pydantic domain types, zero I/O |
| `tests/ports/test_identity_provider.py` | Create | Conformance + neutrality-denylist + no-adapter-import tests |

## Interfaces / Contracts

```python
# identity/types.py  (pydantic BaseModel, mirrors pipeline/types.py)
class AuthenticationRequest(BaseModel):
    audience: str                       # platform surface being accessed
    context: dict[str, str] = {}        # opaque neutral parameters
class AuthenticationChallenge(BaseModel):
    challenge_id: str
    payload: str                        # opaque blob relayed to the provider
class IdentityAssertion(BaseModel):
    challenge_id: str
    value: str                          # opaque provider artifact (not "code"/"jwt")
class SessionRef(BaseModel):
    reference: str                      # opaque pointer; never a credential
class AuthenticatedPrincipal(BaseModel):
    subject: str                        # stable opaque external identity ref
    claims: dict[str, str] = {}         # transient attributes for role mapping
    session: SessionRef

# ports/identity_provider.py
@runtime_checkable
class IdentityProvider(Protocol):
    def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge: ...
    def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal: ...
    def resolve(self, session: SessionRef) -> AuthenticatedPrincipal: ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Structural fake with `object`-typed params satisfies `isinstance(_, IdentityProvider)` | `runtime_checkable` NAMES-only conformance |
| Unit | Class missing one method fails `isinstance` | Negative case |
| Unit | Happy path returns neutral pydantic shapes; `resolve` round-trips a `SessionRef` | Typed `_NeutralProvider` |
| Unit | Docstrings document neutral verbs (verify/principal/session) | `__doc__` assertions |
| Unit | **Neutrality denylist** absent from port + types source | `inspect.getsource` scan |
| Unit | **No adapter/network import** in port | `ast` walk of imports |

Denylist (superstring-safe, excludes broad `auth`): `github, gitlab, google, oidc, oauth,
openid, saml, sso, jwt, bearer, password, credential, ldap, mfa, okta, auth0, keycloak,
cognito, entra, azuread`. Import denylist: `adapter, subprocess, requests, httpx`.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. Pure interface + pydantic types, zero I/O.

## Migration / Rollout

No migration required. Additive, file-disjoint; rollback = delete the four new paths.

## Open Questions

- None blocking. `DPROV-IDP` (first IdP) and mapping-source granularity are downstream
  adapter/RBAC concerns, explicitly out of scope for this contract.
