"""Identity port — interface only, no adapter in this slice.

`odoo_forge` depends only on this structural interface. No concrete identity
provider is chosen here (selecting one is out of scope for this slice); the
future adapter that maps these neutral operations onto a specific provider
MUST NOT be imported by this module.

`from __future__ import annotations` keeps every annotation a lazy string, so
this module never needs a runtime import of `identity.types`
(`AuthenticationRequest`/`AuthenticationChallenge`/`IdentityAssertion`/
`SessionRef`/`AuthenticatedPrincipal`). `runtime_checkable` only inspects
method NAMES at runtime, so lazy annotations do not weaken the `isinstance`
conformance check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from odoo_forge.identity.types import (
        AuthenticatedPrincipal,
        AuthenticationChallenge,
        AuthenticationRequest,
        IdentityAssertion,
        SessionRef,
    )


@runtime_checkable
class IdentityProvider(Protocol):
    def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge:
        """Start an authentication attempt; return an opaque challenge to relay."""
        ...

    def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal:
        """Exchange a completed assertion for a verified principal and its claims."""
        ...

    def resolve(self, session: SessionRef) -> AuthenticatedPrincipal:
        """Re-establish the principal behind a previously issued session reference."""
        ...


__all__ = ["IdentityProvider"]
