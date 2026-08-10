"""Provider-neutral GitHub identity adapter with bounded JOSE verification."""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
from collections.abc import Mapping

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

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
_TOKEN_SEGMENTS = 3


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
        self._required_claims = required_claims

    def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge:
        """Create a stateless opaque challenge containing only the audience."""
        audience = request.audience
        if not audience.strip():
            raise ValueError("audience must not be empty")
        challenge = _encode_audience(audience)
        return AuthenticationChallenge(challenge_id=challenge, payload=challenge)

    def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal | None:
        """Return a neutral principal only after complete assertion validation."""
        try:
            audience = self._recover_audience(assertion.challenge_id)
            metadata = self._transport.get_metadata(self._issuer)
            if metadata.get("issuer") != self._issuer:
                return None
            jwks_uri = metadata.get("jwks_uri")
            if not isinstance(jwks_uri, str) or not jwks_uri:
                return None
            jwks = self._transport.get_jwks(jwks_uri)
            if not isinstance(jwks.get("keys"), list):
                return None
            header, claims, signing_input, signature = _parse_token(assertion.value)
            if header.get("alg") != "RS256" or "crit" in header:
                return None
            key = _select_key(jwks["keys"], header.get("kid"))
            key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
            _validate_claims(
                claims,
                issuer=self._issuer,
                audience=audience,
                required_claims=self._required_claims,
            )
            subject = claims["sub"]
            translated_claims: dict[str, str] = {}
            for claim in self._required_claims:
                value = claims[claim]
                if not isinstance(value, str):
                    return None
                translated_claims[claim] = value
            if not isinstance(subject, str):
                return None
            return self._translate_principal(subject, translated_claims)
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


def _parse_token(token: str) -> tuple[dict[str, object], dict[str, object], bytes, bytes]:
    segments = token.split(".")
    if len(segments) != _TOKEN_SEGMENTS or any(
        not _CHALLENGE_CHARS.fullmatch(segment) for segment in segments
    ):
        raise ValueError("malformed compact JWT")
    header = _decode_object(_decode_segment(segments[0]))
    claims = _decode_object(_decode_segment(segments[1]))
    signature = _decode_segment(segments[2])
    signing_input = f"{segments[0]}.{segments[1]}".encode("ascii")
    return header, claims, signing_input, signature


def _decode_segment(segment: str) -> bytes:
    if len(segment) % 4 == 1:
        raise ValueError("malformed compact JWT")
    try:
        return base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("malformed compact JWT") from exc


def _decode_object(payload: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed compact JWT") from exc
    if not isinstance(decoded, dict):
        raise ValueError("malformed compact JWT")
    return decoded


def _select_key(keys: object, kid: object) -> rsa.RSAPublicKey:
    if not isinstance(kid, str) or not kid:
        raise ValueError("missing JWT key identifier")
    if not isinstance(keys, list):
        raise ValueError("malformed JWKS")
    for key in keys:
        if not isinstance(key, Mapping) or key.get("kid") != kid:
            continue
        if (
            key.get("kty") != "RSA"
            or key.get("use") != "sig"
            or key.get("alg") not in (None, "RS256")
        ):
            raise ValueError("unsuitable JWKS key")
        modulus = _decode_integer(key.get("n"))
        exponent = _decode_integer(key.get("e"))
        try:
            return rsa.RSAPublicNumbers(exponent, modulus).public_key()
        except ValueError as exc:
            raise ValueError("invalid RSA JWKS key") from exc
    raise ValueError("unknown JWT key identifier")


def _decode_integer(value: object) -> int:
    if not isinstance(value, str) or not value:
        raise ValueError("invalid RSA JWKS key material")
    number = int.from_bytes(_decode_segment(value), "big")
    if number <= 0:
        raise ValueError("invalid RSA JWKS key material")
    return number


def _validate_claims(
    claims: Mapping[str, object],
    *,
    issuer: str,
    audience: str,
    required_claims: tuple[str, ...],
) -> None:
    if claims.get("iss") != issuer or claims.get("aud") != audience:
        raise ValueError("issuer or audience mismatch")
    subject = claims.get("sub")
    expiry = claims.get("exp")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject must be a non-empty string")
    if type(expiry) is not int or expiry <= time.time():
        raise ValueError("expiration is invalid or expired")
    for claim in required_claims:
        value = claims.get(claim)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("required claim is invalid")


__all__ = ["GitHubIdentityProvider"]
