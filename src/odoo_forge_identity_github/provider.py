"""Provider-neutral GitHub identity adapter before JOSE verification."""

from __future__ import annotations

import base64
import binascii
import re

from odoo_forge.identity.types import (
    AuthenticatedPrincipal,
    AuthenticationChallenge,
    AuthenticationRequest,
    IdentityAssertion,
    SessionRef,
)
from odoo_forge_identity_github.transport import GitHubOidcTransport

DEFAULT_ISSUER = "https://token.actions.githubusercontent.com"
_CHALLENGE_CHARS = re.compile(r"[A-Za-z0-9_-]+")


class GitHubIdentityProvider:
    """Adapt the neutral identity port to the bounded GitHub OIDC seam."""

    def __init__(
        self,
        *,
        transport: GitHubOidcTransport,
        issuer: str = DEFAULT_ISSUER,
        required_claims: tuple[str, ...],
    ) -> None:
        if not issuer.strip():
            raise ValueError("issuer must not be empty")
        if not required_claims or any(not claim.strip() for claim in required_claims):
            raise ValueError("required claims must be non-empty names")
        self._transport = transport
        self._issuer = issuer

    def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge:
        """Create a stateless opaque challenge containing only the audience."""
        audience = request.audience
        if not audience.strip():
            raise ValueError("audience must not be empty")
        challenge = _encode_audience(audience)
        return AuthenticationChallenge(challenge_id=challenge, payload=challenge)

    def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal | None:
        """Reject after bounded discovery until JOSE verification is implemented."""
        try:
            self._recover_audience(assertion.challenge_id)
            metadata = self._transport.get_metadata(self._issuer)
            if metadata.get("issuer") != self._issuer:
                return None
            jwks_uri = metadata.get("jwks_uri")
            if not isinstance(jwks_uri, str) or not jwks_uri:
                return None
            jwks = self._transport.get_jwks(jwks_uri)
            if not isinstance(jwks.get("keys"), list):
                return None
            return None
        except Exception:
            return None

    def resolve(self, session: SessionRef) -> AuthenticatedPrincipal:
        """Fail closed because no accepted session-resolution contract exists."""
        raise NotImplementedError("session resolution is unsupported")

    @staticmethod
    def _recover_audience(challenge_id: str) -> str:
        if not challenge_id or _CHALLENGE_CHARS.fullmatch(challenge_id) is None:
            raise ValueError("malformed authentication challenge")
        padding = "=" * (-len(challenge_id) % 4)
        try:
            audience = base64.urlsafe_b64decode(challenge_id + padding).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError("malformed authentication challenge") from exc
        if not audience.strip() or _encode_audience(audience) != challenge_id:
            raise ValueError("malformed authentication challenge")
        return audience

    @staticmethod
    def _translate_principal(subject: str, claims: dict[str, str]) -> AuthenticatedPrincipal:
        if not subject.strip() or any(not isinstance(value, str) for value in claims.values()):
            raise ValueError("principal values must be non-empty strings")
        return AuthenticatedPrincipal(
            subject=subject,
            claims=dict(claims),
            session=SessionRef(reference=""),
        )


def _encode_audience(audience: str) -> str:
    return base64.urlsafe_b64encode(audience.encode("utf-8")).decode("ascii").rstrip("=")


__all__ = ["GitHubIdentityProvider"]
