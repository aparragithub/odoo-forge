# Tasks: PORT-IDENTITY — Provider-Neutral Identity Port

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-220 (4 new files: 2 small modules, 1 empty `__init__.py`, 1 test file) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Contract-only port + neutral types + conformance/neutrality tests | PR 1 (single) | `uv run pytest tests/ports/test_identity_provider.py` | N/A — pure interface/types, no I/O, no adapter to exercise | Delete the 4 new files; no shared file touched, no dangling references |

## Phase 1: RED — Failing Tests First

- [x] 1.1 Create `tests/ports/test_identity_provider.py` with a structurally-conforming fake class (`begin`, `verify`, `resolve` methods, `object`-typed params) and assert `isinstance(fake, IdentityProvider)` — MUST fail (import error) since `IdentityProvider` doesn't exist yet.
- [x] 1.2 In the same test file, add a fake missing `resolve()` and assert `not isinstance(fake, IdentityProvider)`.
- [x] 1.3 Add `begin` → `verify` happy-path test using a typed `_NeutralProvider` fake and neutral types (`AuthenticationRequest`, `AuthenticationChallenge`, `IdentityAssertion`, `AuthenticatedPrincipal`), asserting the returned `AuthenticatedPrincipal` carries no IdP-vendor shape and no raw credential fields.
- [x] 1.4 Add `resolve` round-trip test: a `SessionRef` produced by `verify()` is passed to `resolve()` and returns an equivalent `AuthenticatedPrincipal`.
- [x] 1.5 Add "rejected authentication" scenario test: a fake configured to reject a request is allowed to raise or return a distinct outcome from `verify()` without any IdP-vendor-specific error type at the port level.
- [x] 1.6 Add docstring-boundary test asserting key neutral docstring phrases are present on `begin`/`verify`/`resolve`.
- [x] 1.7 Add the IdP-vendor denylist neutrality test: scan source text of `identity_provider.py` and every module under `src/odoo_forge/identity/` for tokens `github`, `gitlab`, `google`, `oidc`, `oauth`, `openid`, `saml`, `sso`, `jwt`, `bearer`, `password`, `credential`, `ldap`, `mfa`, `okta`, `auth0`, `keycloak`, `cognito`, `entra`, `azuread` (case-insensitive) — assert none present.
- [x] 1.8 Add no-adapter-import test: `ast`-walk `identity_provider.py`'s import statements and assert no import of `adapter`, `subprocess`, `requests`, or `httpx`.
- [x] 1.9 Run `uv run pytest tests/ports/test_identity_provider.py` — confirm all tests fail with `ImportError`/`ModuleNotFoundError` (RED baseline).

## Phase 2: GREEN — Minimal Implementation

- [x] 2.1 Create `src/odoo_forge/identity/__init__.py` as an empty package marker.
- [x] 2.2 Create `src/odoo_forge/identity/types.py`: `AuthenticationRequest(BaseModel)` (`audience: str`, `context: dict[str, str] = {}`), `AuthenticationChallenge(BaseModel)` (`challenge_id: str`, `payload: str`), `IdentityAssertion(BaseModel)` (`challenge_id: str`, `value: str`), `SessionRef(BaseModel)` (`reference: str`), `AuthenticatedPrincipal(BaseModel)` (`subject: str`, `claims: dict[str, str] = {}`, `session: SessionRef`); define `__all__`.
- [x] 2.3 Create `src/odoo_forge/ports/identity_provider.py`: `from __future__ import annotations`; `TYPE_CHECKING`-guarded import of `identity.types`; `@runtime_checkable class IdentityProvider(Protocol)` with `begin(request) -> AuthenticationChallenge`, `verify(assertion) -> AuthenticatedPrincipal`, `resolve(session) -> AuthenticatedPrincipal`, neutral docstrings on each method; define `__all__`. No adapter import.
- [x] 2.4 Run `uv run pytest tests/ports/test_identity_provider.py` — confirm all tests pass (GREEN).

## Phase 3: REFACTOR — Cleanup and Verification

- [x] 3.1 Review method/docstring wording in `identity_provider.py` and `identity/types.py` for minimality and consistency with `pipeline_provider.py` / `pipeline/types.py` style; no behavior change.
- [x] 3.2 Confirm `src/odoo_forge/ports/__init__.py` is unchanged and still empty (no re-exports added).
- [x] 3.3 Confirm no edits touch `pyproject.toml`, `manifest/schema.py`, `credentials/*`, `src/odoo_forge_cli/*`, `tenancy/*`, `pipeline/*`, or any adapter path.
- [x] 3.4 Run `uv run lint-imports` — confirm no import-boundary violation introduced.
- [x] 3.5 Run `uv run mypy` — confirm no type errors on the new modules (1 pre-existing unrelated error remains in `tests/cli/test_backend.py`, confirmed present on baseline via `git stash`).
- [x] 3.6 Run `uv run ruff check` — confirm no lint violations on the new modules (1 pre-existing unrelated violation remains in `src/odoo_forge_postgres_docker/provider.py`, introduced by an earlier commit, not this change).
- [x] 3.7 Re-run `uv run pytest tests/ports/test_identity_provider.py` — confirm still GREEN after cleanup.
