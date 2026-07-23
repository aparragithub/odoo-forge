# Identity Provider Specification

## Purpose

Define the provider-neutral structural port contract that `odoo_forge` core
depends on to authenticate a platform user against an organization identity
provider and obtain neutral identity claims — without importing or naming any
concrete IdP. Adapters, role models, session storage, and credential
persistence are out of scope; only the abstract interface, its neutral
domain types, and its neutrality invariant are specified here.

## Requirements

### Requirement: Structural Identity Port

The system MUST expose a `runtime_checkable` `Protocol` named
`IdentityProvider` in `src/odoo_forge/ports/identity_provider.py` that core
code depends on exclusively through structural typing, with no import of any
concrete adapter.

#### Scenario: Structural conformance via isinstance

- GIVEN a plain class that implements every method the port declares, with
  matching method names
- WHEN checked with `isinstance(fake, IdentityProvider)`
- THEN the check MUST pass without the fake class inheriting from
  `IdentityProvider`

#### Scenario: Non-conforming object is rejected

- GIVEN an object missing one or more of the port's declared methods
- WHEN checked with `isinstance(obj, IdentityProvider)`
- THEN the check MUST fail

### Requirement: Provider-Neutral Identity Domain Types

The system MUST define IdP-agnostic pydantic domain types under
`src/odoo_forge/identity/types.py` covering, at minimum: an authentication
request, resolved identity claims, and an opaque session-or-token reference.
These types MUST express only role-mapping-relevant identity vocabulary —
never a raw credential (password, secret, private key) or a mirrored
user-directory record. Exact field names/signatures are a design decision,
not fixed by this spec.

#### Scenario: Authenticate and receive neutral claims

- GIVEN a structurally conforming fake `IdentityProvider` and a
  provider-neutral authentication request
- WHEN the port's authenticate operation is invoked with that request
- THEN the result MUST be a provider-neutral identity-claims type containing
  no IdP-vendor-specific shape and no raw credential material

#### Scenario: Rejected authentication attempt

- GIVEN a fake `IdentityProvider` configured to reject a given request
- WHEN the port's authenticate operation is invoked with that request
- THEN the port's contract MUST allow the implementation to signal
  "not authenticated" (e.g. raise or return a distinct outcome) without
  requiring any IdP-vendor-specific error type at the port level

### Requirement: IdP-Vendor Neutrality Invariant

The port module, the `src/odoo_forge/identity/` domain-type modules, and
their docstrings MUST NOT name or assume a specific identity provider (e.g.
no vendor-specific product names such as GitHub, GitLab, Google, or
protocol/handshake specifics such as OIDC/SAML wiring details). All
vocabulary MUST stay at the level of "identity", "claims", "authenticate",
"session"/"token reference" — provider-neutral terms only.

#### Scenario: Denylist source-scan assertion

- GIVEN the source text of `identity_provider.py` and every module under
  `src/odoo_forge/identity/`
- WHEN scanned for a fixed denylist of IdP-vendor-specific tokens and
  protocol-handshake tokens
- THEN none of the denylisted tokens MUST appear

#### Scenario: No adapter import

- GIVEN the port module's import statements
- WHEN inspected
- THEN no import of a concrete identity adapter or IdP-vendor-specific
  package MUST be present
